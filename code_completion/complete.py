import os, sys, pickle, pymysql, argparse
import torch.cuda
from tqdm import tqdm

from models import MODEL_FACTORY, CodeLLMCompletionEngine, GLMCompletionEngine

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from global_config import DB_CONFIG, GITHUB_CODE_DOWNLOAD_BASE_DIR, RESULT_BASE_DIR
from task_construction.get_api_signatures import get_API_calls_from_funcnode
from task_construction.api_extractor      import build_package_version_dict
from task_construction.version_resolver   import get_all_dependencies

COMPLETION_RESULT_DIR = os.path.join(RESULT_BASE_DIR, 'completion')

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument('-m', '--model', help='model name', type=str, required=True)
arg_parser.add_argument('-o', '--omit', help='omit version info', action='store_true')
arg_parser.add_argument('-f', '--func', help='complete function level tasks', action='store_true')
arg_parser.add_argument('-g', '--gpu',  help='GPU index', type=int, default=6)

DATA_BASE_DIR = GITHUB_CODE_DOWNLOAD_BASE_DIR
MAX_CTX_LINE = 100

def query_api_task_info(cursor, tid: int):
    cursor.execute(f"SELECT * FROM api_calls WHERE id={tid}")
    _, fqn, abs_file, start, end, _, constrain_str = cursor.fetchone()

    tpl = fqn.split('.')[0]
    relative_dir = abs_file[len(DATA_BASE_DIR)+1:]
    repo, file = relative_dir.split('/', 1)

    return tpl, repo, file, start, end, constrain_str

def query_func_task_info(cursor, tid: int):
    cursor.execute(f"SELECT * FROM func_task WHERE id={tid}")
    _, fqn, abs_file, start, end, _, constrain_str, bg_off, ed_off = cursor.fetchone()

    tpl = fqn.split('.')[0]
    relative_dir = abs_file[len(DATA_BASE_DIR)+1:]
    repo, file = relative_dir.split('/', 1)

    return tpl, repo, file, start, end, constrain_str, bg_off, ed_off


def pred_api_level(min_idx, MODEL, cursor, OMIT):
    with open('API_Level_Tids.pkl', 'rb') as f:
        tids = pickle.load(f)

    for idx in tqdm(range(min_idx, len(tids))):
        tid = tids[idx]

        # construct task
        tpl, repo, file, start, end, constrain_str = query_api_task_info(cursor, tid)
        try:
            task = APILevelTask(
                tpl=tpl, version=constrain_str,
                repo=repo, file=file,
                gt_start_lineno=start-1,
                rctx_start_lineno=end
            )
        except Exception as e:
            print(e)
            exit(0)
            
        # predict
        if MODEL=='codegen-6b': res = engine.complete(task, omit=OMIT, max_len=2048)
        else:                   res = engine.complete(task, omit=OMIT)

        # serialize
        complete_res = (tid, res)
        with open(f'{COMPLETION_RESULT_DIR}/{MODEL}_{OMIT}_API_Completion.pkl', 'ab') as f:
            pickle.dump(complete_res, f)
        with open(f'{COMPLETION_RESULT_DIR}/{MODEL}_{OMIT}_API_max_task.txt', 'w', encoding='utf-8') as f:
            f.write(str(idx))

    return

def pred_func_level(min_idx, MODEL, cursor, OMIT):
    with open('Func_Level_Tids.pkl', 'rb') as f:
        tids = pickle.load(f)

    for idx in tqdm(range(min_idx, len(tids))):
        tid = tids[idx]

        tpl, repo, file, start, end, constrain_str, bg_off, ed_off = query_func_task_info(cursor, tid)
        
        task = FunctionLevelTask(
            bg_off, ed_off,
            tpl=tpl, version=constrain_str,
            repo=repo, file=file,
            gt_start_lineno=start-1,
            rctx_start_lineno=end
        )

        # predict
        if MODEL=='codegen-6b': res = engine.complete(task, omit=OMIT, max_len=2048)
        else:                   res = engine.complete(task, omit=OMIT)

        if not res:
            stmt = ''
        else:
            deps = get_all_dependencies(os.path.join(DATA_BASE_DIR, repo))
            dep_dict = build_package_version_dict(deps)
            func_src = f'{task.head}\n{res}'
            func_calls = get_API_calls_from_funcnode(func_src, '', dep_dict, task.class2obj, task.instance2class, task.id2fullname)
            if not func_calls:
                stmt = ''
            else:
                bg_off, ed_off = func_calls[0]['lineno'], func_calls[0]['end_lineno']
                lines = func_src.split('\n')
                stmt = ''.join(lines[bg_off-1:ed_off]).strip()
            
        # serialize
        complete_res = (tid, res, stmt)
        with open(f'{COMPLETION_RESULT_DIR}/{MODEL}_{OMIT}_Func_Completion.pkl', 'ab') as f:
            pickle.dump(complete_res, f)
        with open(f'{COMPLETION_RESULT_DIR}/{MODEL}_{OMIT}_Func_max_task.txt', 'w', encoding='utf-8') as f:
            f.write(str(idx))
    return

if __name__ == '__main__':
    # parse args
    args = arg_parser.parse_args()
    MODEL = args.model
    OMIT  = args.omit
    FUNC  = args.func
    print(f'[Info] Using Model "{MODEL}" {"(OMIT) " if OMIT else ""}for {"FUNC" if FUNC else "API"} Level Tasks')

    GPU   = args.gpu
    if torch.cuda.is_available():
        print(f'[Info] Using GPU ({GPU})')
        torch.cuda.set_device(GPU)
    
    # select model
    valid_models = list(MODEL_FACTORY.keys())
    if not MODEL in valid_models:
        print(f'[Err] Invalide model: "{MODEL}". Please select from: {valid_models}')
        exit(0)
    print(f'[LOG] Sample: using model "{MODEL}"')

    # init engine
    if MODEL in ['deepseek-v3', 'gpt-4o']:
        client, model, price = MODEL_FACTORY[MODEL]()
        engine = GLMCompletionEngine(client, model, price)
    elif MODEL in ['gemini-2.5-flash']:
        client, model, price = MODEL_FACTORY[MODEL]()
        engine = GLMCompletionEngine(client, model, price, useGemini=True)
    else:
        model, tokenizer = MODEL_FACTORY[MODEL]()
        engine = CodeLLMCompletionEngine(model, tokenizer)
    print('[LOG] Model initialized')

    # recover
    try:
        with open(f'{COMPLETION_RESULT_DIR}/{MODEL}_{OMIT}_{"Func" if FUNC else "API"}_max_task.txt', 'r', encoding='utf-8') as f:
            min_idx = int(f.read())+1
        print(f'[LOG] Recover from task_id {min_idx}')
    except Exception:
        min_idx = 0
        print(f'[LOG] Start from scratch')
    
    with pymysql.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cursor:
            if FUNC:
                pred_func_level(min_idx, MODEL, cursor, OMIT)
            else:
                pred_api_level(min_idx, MODEL, cursor, OMIT)
