from typing import List, Dict

class PromptBuilder:
    def __init__(self, model_name: str = "qwen"):
        self.model_name = model_name.lower()
        # 默认系统指令：强制要求模型使用 Markdown 格式输出代码块
        self.default_system_prompt = """你是一个专业的 AI 助手。请遵循以下规则：
1. 当输出代码时，必须使用 Markdown 代码块格式，并在开头标注语言类型。
2. 使用清晰的 Markdown 格式（标题、列表、粗体等）组织回答。
3. 保持回答简洁专业。"""

    def build_prompt(self, history_text: str, current_input: str, system_prompt: str = None) -> str:
        """根据模型类型构建完整的 Prompt"""
        # 如果传入了特定的系统提示词（如代码模式），则覆盖默认的
        active_system = system_prompt if system_prompt else self.default_system_prompt
        
        # 在历史记录的开头加入系统指令（使用明确标记）
        if history_text.strip():
            full_history = f"[系统指令]\n{active_system}\n\n[历史对话]\n{history_text}"
        else:
            full_history = f"[系统指令]\n{active_system}"
        
        if "gemma" in self.model_name:
            return self._build_gemma_prompt(full_history, current_input)
        elif "llama" in self.model_name:
            return self._build_llama_prompt(full_history, current_input)
        else:
            # 默认使用 Qwen 格式
            return self._build_qwen_prompt(full_history, current_input)

    def _build_qwen_prompt(self, history: str, input: str) -> str:
        # 使用明确的分隔符，防止模型混淆历史和当前输入
        if history.strip():
            # 有历史记录的情况
            return f"{history}\n\n[当前问题]\n{input}\n[开始回答]\n"
        else:
            # 无历史记录（首次对话）
            return f"{input}\n[开始回答]\n"

    def _build_gemma_prompt(self, history: str, input: str) -> str:
        # Gemma 使用 <start_of_turn> 标签
        return f"{history}<start_of_turn>user\n{input}<end_of_turn>\n<start_of_turn>model\n"

    def _build_llama_prompt(self, history: str, input: str) -> str:
        # Llama-3 使用 <|start_header_id|> 标签
        return f"{history}<|start_header_id|>user<|end_header_id|>\n\n{input}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
