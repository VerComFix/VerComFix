import pickle, os, sys, pymysql, argparse
from tqdm import tqdm

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from global_config import DB_CONFIG, RESULT_BASE_DIR
from code_completion.complete import query_api_task_info
from code_completion.tasks    import APILevelRepairTask
from code_completion.eval     import get_normed_fqn, REPAIR_TASK_DIR
from code_completion.myTypes  import CompletionType
from code_completion.utils    import get_completion_type
from task_construction.arg_validity_checker import ArgumentsAnalyser

REPAIR_RES_DIR = os.path.join(RESULT_BASE_DIR, 'repaired')

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument('-m', '--model', help='model name', type=str, required=True)

conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

if __name__ == '__main__':
    args  = arg_parser.parse_args()
    MODEL = args.model
    print(f'[LOG] Evaluating Repairment of {MODEL}')

    try:
        with open(f'{REPAIR_RES_DIR}/{MODEL}.pkl','rb') as f:
            repaired = pickle.load(f)
        with open(f'{REPAIR_TASK_DIR}/{MODEL}.pkl','rb') as f:
            todos = pickle.load(f)
    except Exception:
        print('[WARN] Please run eval.py first.')
        exit(0)

    sig_match, cr = 0, 0
    for todo, repair in tqdm(zip(todos, repaired)):
        tid, stmt, pred_fqn, desc, api_sig = todo
        _, repair_stmt = repair

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

        if repair_stmt:
            # EM
            repair_stmt.replace(" ", "").replace("\n", "")
            gt_stmt = task.gt.replace(" ", "").replace("\n", "")

            if(repair_stmt==gt_stmt):
                cr += 1
                continue
    
            repair_fqn, repair_call_str, repair_call_node = get_normed_fqn(task, repair_stmt, True)
            gt_fqn,     gt_call_str,     gt_call_node     = get_normed_fqn(task, gt_stmt,     True)

            # API Name Match
            if gt_fqn in [repair_fqn, task.orig_pred_api_name]:
                sig_match += 1

                # args
                try:
                    repair_args = ArgumentsAnalyser(repair_call_str).extract_arguments_info(repair_call_node)
                except Exception as e:
                    repair_args = {'keyword_args':[], 'positional_args':[]}
                try: 
                    gt_args = ArgumentsAnalyser(gt_call_str).extract_arguments_info(gt_call_node)
                except Exception as e:
                    gt_args = {'keyword_args':[], 'positional_args':[]}
                
                repair_keywords = [item['keyword_name'] for item in repair_args['keyword_args']]
                gt_keywords     = [item['keyword_name'] for item in gt_args['keyword_args']]

                diff_keywords = set(repair_keywords) - set(gt_keywords)
                diff_arg_num  = ((len(repair_args['keyword_args'])+len(repair_args['positional_args']))!=(len(gt_args['keyword_args'])+len(gt_args['positional_args'])))

                if diff_keywords or diff_arg_num:
                    c_type, _ = get_completion_type(api_sig, repair_stmt, repair_fqn, api_sig[0])
                else: 
                    c_type = CompletionType.CR

                if c_type == CompletionType.CR: cr += 1

    print(f'RIGHT FQN: {sig_match} ({sig_match*100.0/len(todos)})')
    print(f'RSR:  {cr} ({cr*100.0/len(todos)})')
