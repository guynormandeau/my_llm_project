# app.py

import os
import logging
from dotenv import load_dotenv
import chromadb
import gradio as gr
from huggingface_hub import snapshot_download

from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.memory import ChatSummaryMemoryBuffer
from llama_index.core.tools import RetrieverTool, ToolMetadata
from llama_index.agent.openai import OpenAIAgent
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.core.llms import MessageRole

# Load environment
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

PROMPT_SYSTEM_MESSAGE = """You are an AI teacher, answering questions from students of an applied AI course on Large Language Models (LLMs or llm) and Retrieval Augmented Generation (RAG) for LLMs. 
Topics covered include training models, fine-tuning models, giving memory to LLMs, prompting tips, hallucinations and bias, vector databases, transformer architectures, embeddings, RAG frameworks such as 
Langchain and LlamaIndex, making LLMs interact with tools, AI agents, reinforcement learning with human feedback (RLHF). Questions should be understood in this context. Your answers are aimed to teach 
students, so they should be complete, clear, and easy to understand. Use the available tools to gather insights pertinent to the field of AI.
To find relevant information for answering student questions, always use the "AI_Information_related_resources" tool.

Only some information returned by the tool might be relevant to the question, so ignore the irrelevant part and answer the question with what you have. Your responses are exclusively based on the output provided 
by the tools. Refrain from incorporating information not directly obtained from the tool's responses.
If a user requests further elaboration on a specific aspect of a previously discussed topic, you should reformulate your input to the tool to capture this new angle or more profound layer of inquiry. Provide 
comprehensive answers, ideally structured in multiple paragraphs, drawing from the tool's variety of relevant details. The depth and breadth of your responses should align with the scope and specificity of the information retrieved. 
Should the tool response lack information on the queried topic, politely inform the user that the question transcends the bounds of your current knowledge base, citing the absence of relevant content in the tool's documentation. 
At the end of your answers, always invite the students to ask deeper questions about the topic if they have any.
Do not refer to the documentation directly, but use the information provided within it to answer questions. If code is provided in the information, share it with the students. It's important to provide complete code blocks so 
they can execute the code when they copy and paste them. Make sure to format your answers in Markdown format, including code blocks and snippets."""

TEXT_QA_TEMPLATE = """You must answer only related to AI, ML, Deep Learning and related concepts queries.
Always leverage the retrieved documents to answer the questions, don't answer them on your own.
If the query is not relevant to AI, say that you don't know the answer."""

# Download knowledge base if missing
def download_knowledge_base_if_not_exists():
    if not os.path.exists("data/ai_tutor_knowledge"):
        os.makedirs("data/ai_tutor_knowledge")
        snapshot_download(
            repo_id="jaiganesan/ai_tutor_knowledge_vector_Store",
            local_dir="data/ai_tutor_knowledge",
            repo_type="dataset",
        )

# Define retriever tool
def get_tools(db_collection="ai_tutor_knowledge"):
    db = chromadb.PersistentClient(path=f"data/{db_collection}")
    chroma_collection = db.get_or_create_collection(db_collection)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        show_progress=True,
        use_async=True,
        embed_model=Settings.embed_model
    )
    retriever = VectorIndexRetriever(index=index, similarity_top_k=15, embed_model=Settings.embed_model)
    return [
        RetrieverTool(
            retriever=retriever,
            metadata=ToolMetadata(
                name="AI_Information_related_resources",
                description="Useful for info related to artificial intelligence, ML, deep learning."
            )
        )
    ]

# Factory to generate a function with memory
def generate_completion_factory(memory):
    def generate_completion(query, history):
        try:
            chat_list = memory.get()
            if len(chat_list) != 0:
                user_index = [i for i, msg in enumerate(chat_list) if msg.role == MessageRole.USER]
                if len(user_index) > len(history):
                    chat_list = chat_list[:user_index[user_index[-1]]]
                    memory.set(chat_list)

            tools = get_tools()
            agent = OpenAIAgent.from_tools(
                llm=Settings.llm,
                memory=memory,
                tools=tools,
                system_prompt=PROMPT_SYSTEM_MESSAGE
            )

            completion = agent.stream_chat(query)
            answer = ""
            for token in completion.response_gen:
                answer += token
                yield answer

        except Exception as e:
            logging.error(f"Error during generate_completion: {e}")
            yield f"❌ Error: {e}"

    return generate_completion

# Gradio UI
def launch_ui():
    memory = ChatSummaryMemoryBuffer.from_defaults(token_limit=120000)
    generate_completion = generate_completion_factory(memory)

    with gr.Blocks(title="AI Tutor 🤖", fill_height=True) as demo:
        chatbot = gr.Chatbot(
            placeholder="<strong>AI Tutor 🤖: Ask me anything about AI!</strong><br>",
            show_label=False,
            show_copy_button=True
        )

        gr.ChatInterface(
            fn=generate_completion,
            chatbot=chatbot
        )

        demo.queue(default_concurrency_limit=64)
        demo.launch(debug=True)  # `share=True` inutile ici

# Init
if __name__ == "__main__":
    download_knowledge_base_if_not_exists()
    Settings.llm = OpenAI(api_key=api_key, temperature=0, model="gpt-4o-mini")
    Settings.embed_model = OpenAIEmbedding(api_key=api_key, model="text-embedding-3-small")
    launch_ui()