from openai import OpenAI

client = OpenAI()

def get_llm_models():
    models = client.models.list()
    return [model.id for model in models.data]

# Usage
llm_models = get_llm_models()
print(llm_models)

