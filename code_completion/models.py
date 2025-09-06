import openai
from os import getenv
from abc import ABC, abstractmethod
from torch import cuda, bfloat16
from transformers import AutoTokenizer, PreTrainedTokenizerBase
from transformers import AutoModelForCausalLM, LlamaForCausalLM, PreTrainedModel

from tasks import Task, APILevelTask, APILevelRepairTask, FunctionLevelTask
from utils import CodeHandler as CH

DEVICE = 'cuda' if cuda.is_available() else 'cpu'

def _init_starcoder2_7b(model_path: str = "bigcode/starcoder2-7b"):
    model = AutoModelForCausalLM\
        .from_pretrained(model_path, trust_remote_code=True, torch_dtype=bfloat16)\
        .to(DEVICE)
    tokenizer = AutoTokenizer\
        .from_pretrained(model_path, trust_remote_code=True, padding_side='left')
    tokenizer.pad_token_id = tokenizer.eos_token_id
    return model, tokenizer

def _init_codegen_6b(model_path: str = "Salesforce/codegen-6B-nl"):
    model = AutoModelForCausalLM\
        .from_pretrained(model_path, torch_dtype=bfloat16)\
        .to(DEVICE)
    tokenizer = AutoTokenizer\
        .from_pretrained(model_path, trust_remote_code=True, padding_side='left')
    tokenizer.pad_token_id = tokenizer.eos_token_id
    return model, tokenizer

def _init_codellama_7b_instruct(model_path: str = "codellama/CodeLlama-7b-Instruct-hf"):
    model = LlamaForCausalLM\
        .from_pretrained(model_path, torch_dtype=bfloat16, device_map=DEVICE)
    tokenizer = AutoTokenizer\
        .from_pretrained(model_path, padding_side="left")
    tokenizer.pad_token_id = tokenizer.eos_token_id
    return model, tokenizer

def _init_deepseek_coder_7b_instruct(model_path: str = "deepseek-ai/deepseek-coder-6.7b-instruct"):
    model = AutoModelForCausalLM\
        .from_pretrained(model_path, trust_remote_code=True, torch_dtype=bfloat16)\
        .to(DEVICE)
    tokenizer = AutoTokenizer\
        .from_pretrained(model_path, trust_remote_code=True, padding_side='left')
    tokenizer.pad_token_id = tokenizer.eos_token_id
    return model, tokenizer

def _init_deepseek_r1_distill_llama_8b(model_path: str = "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"):
    model = AutoModelForCausalLM\
        .from_pretrained(model_path, trust_remote_code=True, torch_dtype=bfloat16)\
        .to(DEVICE)
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    return model, tokenizer

def _init_gpt_4o():
    # double check
    # input("[Warn] You are using GPT-4o model, press Enter to continue...")

    token = getenv('OPENAI_API_KEY')
    if not token:
        print('[Err] Please set environment variable "OPENAI_API_KEY"')
        exit(0)
    return openai.OpenAI(
        api_key=token,
        base_url='https://api.openai-proxy.org/v1'
    ), "gpt-4o", (2.5*1.5 / 1E6, 10*1.5 / 1E6) # CloseAI 的定价

MODEL_FACTORY = {
    # CodeLLM
    "codegen-6b":            _init_codegen_6b,
    "starcoder2-7b":         _init_starcoder2_7b,
    "codellama-7b-instruct": _init_codellama_7b_instruct,
    "deepseek-coder-6.7b":   _init_deepseek_coder_7b_instruct,
    "deepseek_r1_distill":   _init_deepseek_r1_distill_llama_8b,
    # GLM
    "gpt-4o":                _init_gpt_4o,
}

class CompletionEngine(ABC):
    @abstractmethod
    def complete(self, omit: bool = False): pass

    def max_len(self, task: Task) -> int:
        if isinstance(task, (APILevelTask, APILevelRepairTask)):  return 50
        if isinstance(task, FunctionLevelTask):             return 100


class CodeLLMCompletionEngine(CompletionEngine):
    def __init__(self, model: PreTrainedModel, tokenizer: PreTrainedTokenizerBase):
        self.model = model
        self.model.eval()
        self.tokenizer = tokenizer
        return
    
    """
    输出一个 len == cand_num 的 res 矩阵（已经 decode 好了）
    """
    def complete(self,
        task: Task, 
        beam_size=1,
        # 采用确定性方法（贪婪搜索策略）
        cand_num=1,
        do_sample=False,
        temperature=1.0,
        top_k=None,
        top_p=None,
        # 是否拼接 TPL 知识
        omit: bool = False,
        max_len:int = None
    ) -> str:
        input = task.prompt(omit=omit, is_GPT=False)
        if max_len: # truncate
            ipt_ids = self.tokenizer(
                input, add_special_tokens=True, padding=True, return_tensors="pt",
                truncation=True, max_length=max_len-self.max_len(task)
            ).input_ids\
            .to(self.model.device)
        else:
            ipt_ids = self.tokenizer(
                input, add_special_tokens=True, padding=True, return_tensors="pt"
            ).input_ids\
            .to(self.model.device)
        
        opt_ids = self.model.generate(
            inputs=ipt_ids,
            attention_mask=ipt_ids.ne(self.tokenizer.pad_token_id),
            max_new_tokens = self.max_len(task), 
            num_beams = beam_size,
            num_return_sequences = cand_num,
            do_sample = do_sample,
            temperature = temperature,
            top_k = top_k,
            top_p = top_p,
            pad_token_id=self.tokenizer.eos_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
        )

        generations = [self.tokenizer.decode(ids, skip_special_tokens=True) for ids in opt_ids]
        generations = [gen[len(input):] for gen in generations[:cand_num]]

        return task.handle_completion(generations[0])

class GLMCompletionEngine(CompletionEngine):
    def __init__(self, client: openai.OpenAI, model: str, price: tuple = (0,0)):
        self.model = model
        self.client = client
        # 计费
        self.input_tokens = 0
        self.output_tokens = 0
        self.price = price
        return
    
    def cost(self):
        cost = round(self.input_tokens*self.price[0] + self.output_tokens*self.price[1], 8)
        print((f"\n=== USAGE ===\ninput tokens: {self.input_tokens}, output tokens: {self.input_tokens}, cost: ${cost}"))
        return
    
    def complete(self,
        task: Task,
        omit: bool = False
    ) -> str:
        # send request
        try:
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": task.prompt(omit=omit, is_GPT=True)}],
                model=self.model,
                temperature=0,
                max_tokens=self.max_len(task),
                stream=False
            )
        except openai.APIConnectionError as e:
            print("The server could not be reached")
            print(e.__cause__)
            return ""
        except openai.RateLimitError as e:
            print("A 429 status code was received; we should back off a bit.")
            return ""
        except openai.APIStatusError as e:
            print("Another non-200-range status code was received")
            print(e.status_code)
            print(e.response)
            return ""
        
        # 计费
        self.input_tokens  += response.usage.prompt_tokens
        self.output_tokens += response.usage.completion_tokens
        
        # 后处理: 提取 ``` 之间的代码块
        completion = CH.clean_gpt_response(response.choices[0].message.content)
        return task.handle_completion(completion)
