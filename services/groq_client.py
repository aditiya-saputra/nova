import groq
from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)


class GroqClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = groq.Groq(api_key=settings.GROQ_API_KEY)
        self.model_heavy = settings.GROQ_MODEL_HEAVY
        self.model_fast = settings.GROQ_MODEL_FAST

    def compact(self, history, system_prompt):
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {
                "role": "user",
                "content": "Summarize this conversation concisely, preserving key context, decisions, and important information. Output only the summary."
            }
        ]
        response = self.client.chat.completions.create(
            model=self.model_heavy,
            messages=messages,
            max_completion_tokens=4096,
            temperature=0.3
        )
        return response.choices[0].message.content

    def extract_facts(self, prompt):
        messages = [
            {"role": "system", "content": "You are a fact extractor. Output only valid JSON."},
            {"role": "user", "content": prompt}
        ]
        response = self.client.chat.completions.create(
            model=self.model_heavy,
            messages=messages,
            max_completion_tokens=2048,
            temperature=0.2
        )
        return response.choices[0].message.content

    def retrieve_relevant(self, prompt):
        messages = [
            {"role": "system", "content": "You are a relevance matcher. Output only valid JSON array."},
            {"role": "user", "content": prompt}
        ]
        response = self.client.chat.completions.create(
            model=self.model_heavy,
            messages=messages,
            max_completion_tokens=2048,
            temperature=0.2
        )
        return response.choices[0].message.content

    def process_search_results(self, query, results):
        messages = [
            {"role": "system", "content": "Process search results and provide a concise, accurate summary."},
            {"role": "user", "content": f"Query: {query}\n\nResults:\n{results}"}
        ]
        response = self.client.chat.completions.create(
            model=self.model_fast,
            messages=messages,
            max_completion_tokens=4096,
            temperature=0.3
        )
        return response.choices[0].message.content

    def synthesize(self, context, intent, search_data=None):
        prompt = f"Intent: {intent}\nContext: {context}"
        if search_data:
            prompt += f"\nSearch Data: {search_data}"

        messages = [
            {"role": "system", "content": "Synthesize a helpful, accurate response based on the context and intent."},
            {"role": "user", "content": prompt}
        ]
        response = self.client.chat.completions.create(
            model=self.model_fast,
            messages=messages,
            max_completion_tokens=4096,
            temperature=0.7
        )
        return response.choices[0].message.content
