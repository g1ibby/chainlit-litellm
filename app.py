from datetime import datetime
from typing import List, Optional

import chainlit as cl
import chainlit.data as cl_data
from chainlit.playground.providers import ChatOpenAI
from chainlit.step import StepDict
from chainlit.input_widget import Select, Switch, Slider

from openai import AsyncOpenAI, OpenAI

client = OpenAI()
async_client = AsyncOpenAI()

now = datetime.utcnow().isoformat()
create_step_counter = 0
user_dict = {"id": "test", "createdAt": now, "identifier": "admin"}

thread_history = [
    {
        "id": "test1",
        "metadata": {"name": "thread 1"},
        "createdAt": now,
        "user": user_dict,
        "steps": [
            {
                "id": "test1",
                "name": "test",
                "createdAt": now,
                "type": "user_message",
                "output": "Message 1",
            },
            {
                "id": "test2",
                "name": "test",
                "createdAt": now,
                "type": "assistant_message",
                "output": "Message 2",
            },
        ],
    },
    {
        "id": "test2",
        "createdAt": now,
        "user": user_dict,
        "metadata": {"name": "thread 2"},
        "steps": [
            {
                "id": "test3",
                "createdAt": now,
                "name": "test",
                "type": "user_message",
                "output": "Message 3",
            },
            {
                "id": "test4",
                "createdAt": now,
                "name": "test",
                "type": "assistant_message",
                "output": "Message 4",
            },
        ],
    },
]  # type: List[cl_data.ThreadDict]
deleted_thread_ids = []  # type: List[str]

class TestDataLayer(cl_data.BaseDataLayer):
    async def get_user(self, identifier: str):
        return cl.PersistedUser(id="test", createdAt=now, identifier=identifier)

    async def create_user(self, user: cl.User):
        return cl.PersistedUser(id="test", createdAt=now, identifier=user.identifier)

    @cl_data.queue_until_user_message()
    async def create_step(self, step_dict: StepDict):
        global create_step_counter
        create_step_counter += 1

    async def get_thread_author(self, thread_id: str):
        return "admin"

    async def list_threads(
        self, pagination: cl_data.Pagination, filter: cl_data.ThreadFilter
    ) -> cl_data.PaginatedResponse[cl_data.ThreadDict]:
        return cl_data.PaginatedResponse(
            data=[t for t in thread_history if t["id"] not in deleted_thread_ids],
            pageInfo=cl_data.PageInfo(hasNextPage=False, endCursor=None),
        )

    async def get_thread(self, thread_id: str):
        return next((t for t in thread_history if t["id"] == thread_id), None)

    async def delete_thread(self, thread_id: str):
        deleted_thread_ids.append(thread_id)


cl_data._data_layer = TestDataLayer()

def get_llm_models():
    models = client.models.list()
    print(models)
    return [model.id for model in models.data]

@cl.on_chat_start
async def start():
    cl.user_session.set(
        "message_history",
        [{"role": "system", "content": "You are a helpful assistant."}],
    )
    models = get_llm_models()
    settings = await cl.ChatSettings(
        [
            Select(
                id="Model",
                label="Model",
                values=models,
                initial_index=0,
            ),
            Switch(id="Streaming", label="Stream Tokens", initial=True),
            Slider(
                id="Temperature",
                label="Temperature",
                initial=1,
                min=0,
                max=2,
                step=0.1,
            ),
        ]
    ).send()

@cl.on_settings_update
async def setup_agent(settings):
    print("on_settings_update", settings)

@cl.step(type="llm")
async def answer():
    message_history = cl.user_session.get("message_history")
    msg = cl.Message(author="Answer", content="")
    await msg.send()

    cl_chat_settings = cl.user_session.get("chat_settings")

    settings = {
        "model": cl_chat_settings["Model"],
        "stream": cl_chat_settings["Streaming"],
        "temperature": cl_chat_settings["Temperature"],
    }
    generation = cl.ChatGeneration(
        provider=ChatOpenAI.id,
        settings=settings,
        messages=[
            cl.GenerationMessage(
                formatted=m["content"], name=m.get("name"), role=m["role"]
            )
            for m in message_history
        ],
    )

    msgs = [m.to_openai() for m in generation.messages]
    print(msgs)
    stream = await async_client.chat.completions.create(
        messages=msgs, **settings
    )
    async for part in stream:
        if token := part.choices[0].delta.content or "":
            await msg.stream_token(token)

    message_history.append({"role": "assistant", "content": msg.content})
    msg.update()

    generation.completion = msg.content

    cl.context.current_step.generation = generation

    return msg.content

@cl.on_message
async def main(message: cl.Message):
    message_history = cl.user_session.get("message_history")
    message_history.append({"role": "user", "content": message.content})

    await answer()

@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.User]:
    if (username, password) == ("admin", "admin"):
        return cl.User(identifier="admin")
    else:
        return None

@cl.on_chat_resume
async def on_chat_resume(thread: cl_data.ThreadDict):
    await cl.Message(f"Welcome back to {thread['metadata']['name']}").send()

