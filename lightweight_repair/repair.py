import os, sys, pickle, argparse, pymysql
import torch.cuda
from tqdm import tqdm

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from global_config import DB_CONFIG, GITHUB_CODE_DOWNLOAD_BASE_DIR
from code_completion.complete import query_api_task_info
from code_completion.tasks    import APILevelRepairTask
from code_completion.models   import MODEL_FACTORY, CodeLLMCompletionEngine, GLMCompletionEngine
from code_completion.eval     import REPAIR_TASK_DIR

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument('-m', '--model', help='model name', type=str, required=True)
arg_parser.add_argument('-g', '--gpu',  help='GPU index', type=int, default=6)

DATA_BASE_DIR = GITHUB_CODE_DOWNLOAD_BASE_DIR
MAX_CTX_LINE = 100

conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

if __name__ == '__main__':
    # parse args
    args = arg_parser.parse_args()
    GPU   = args.gpu
    if torch.cuda.is_available():
        print(f'[Info] Using GPU ({GPU})')
        torch.cuda.set_device(GPU)

    # select model
    MODEL = args.model
    valid_models = list(MODEL_FACTORY.keys())
    if not MODEL in valid_models:
        print(f'[Err] Invalide model: "{MODEL}". Please select from: {valid_models}')
        exit(0)
    print(f'[LOG] Sample: using model "{MODEL}"')

    # init engine
    if MODEL in ['deepseek-v3', 'gpt-4o']:
        client, model, price = MODEL_FACTORY[MODEL]()
        engine = GLMCompletionEngine(client, model, price)
    else:
        model, tokenizer = MODEL_FACTORY[MODEL]()
        engine = CodeLLMCompletionEngine(model, tokenizer)
    print('[LOG] Model initialized')

    # load tasks (api_level) => 从对应的 file
    with open(f'{REPAIR_TASK_DIR}/{MODEL}.pkl', 'rb') as f:
        tasks = pickle.load(f)
    
    repaired, results = 0, []
    for task_info in tqdm(tasks):
        tid, stmt, pred_fqn, desc, api_sig = task_info

        # construct task
        tpl, repo, file, start, end, constrain_str = query_api_task_info(cursor, tid)
        task = APILevelRepairTask(
            stmt, pred_fqn,
            desc, api_sig,
            tpl=tpl, version=constrain_str,
            repo=repo, file=file,
            gt_start_lineno=start-1,
            rctx_start_lineno=end
        )

        # pred
        if MODEL=='codegen-6b': res = engine.complete(task, max_len=2048)
        else:                   res = engine.complete(task)
        
        results.append((tid, res))

    # dump
    with open(f'./repaired/{MODEL}.pkl', 'wb') as f:
        pickle.dump(results, f)
