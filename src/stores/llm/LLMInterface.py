from abc import ABC, abstractmethod


class LLMInterface(ABC):

    @abstractmethod
    def set_generation_model(self, model_id: str):
        pass

    @abstractmethod
    def set_embedding_model(self, model_id: str, embedding_size: int = None):
        pass

    @abstractmethod
    def generate_text(self, prompt: str, chat_history: list = [],
                            max_output_tokens: int = None,
                            temperature: float = None):
        pass

    @abstractmethod
    def embed_text(self, text: str, document_type: str = None):
        pass

    @abstractmethod
    def construct_prompt(self, prompt: str, role: str):
        pass

    @abstractmethod
    def get_chat_model(self):
        """
        Returns a LangChain-compatible chat model object that supports
        .bind_tools(...) and .ainvoke(...). Not part of mini_rag's
        LLMInterface - added because this app's agents run a LangGraph
        tool-calling loop directly against the model object, not a single
        prompt-in/text-out generate_text() call.
        """
        pass
