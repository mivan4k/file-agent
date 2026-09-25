
import os
import re
import streamlit as st
from dotenv import load_dotenv
from gigachat import GigaChat
from gigachat.models import ChatCompletionRequest, ChatMessage

# 0. Загрузка данных из config.env
load_dotenv(dotenv_path="config.env")

raw_id = os.getenv("GIGACHAT_CLIENT_ID")
raw_secret = os.getenv("GIGACHAT_CLIENT_SECRET")

if not raw_id or not raw_secret:
    st.error("Ошибка: В файле config.env не заполнены ключи!")
    st.stop()

client_id = raw_id.strip().strip("'").strip('"')
client_secret = raw_secret.strip().strip("'").strip('"')

# 1. Настройка интерфейса
st.set_page_config(page_title="ИИ Файловый Менеджер", page_icon="🗂️")
st.title("🗂️ ИИ-Агент для поиска файлов")
st.write("Напишите название файла, и я подготовлю ссылку на скачивание.")

DOCS_DIR = "my_documents"
if not os.path.exists(DOCS_DIR):
    os.makedirs(DOCS_DIR)


# 2. Функция поиска файлов
def search_file_by_name(query: str) -> str:
    if not os.path.exists(DOCS_DIR):
        return "Папка с файлами пуста или отсутствует."

    matched_files = []
    for root, dirs, files in os.walk(DOCS_DIR):
        for filename in files:
            if query.lower() in filename.lower():
                relative_path = os.path.relpath(os.path.join(root, filename), DOCS_DIR)
                matched_files.append(relative_path)

    if not matched_files:
        return f"Файлы, содержащие в названии '{query}', не найдены."

    return f"Найдены следующие файлы: {', '.join(matched_files)}"


# 3. Инициализация клиента
@st.cache_resource
def get_gigachat_client():
    return GigaChat(
        credentials=client_secret,
        verify_ssl_certs=False
    )


client = get_gigachat_client()

SYSTEM_INSTRUCTION = (
    "Вы — полезный ассистент файлового архива. "
    "В финальном ответе используйте маркер [DOWNLOAD:имя_файла.расширение] для каждого найденного файла. "
    "Пример: Вот ваш файл: [DOWNLOAD:report.pdf]"
)

if "messages" not in st.session_state:
    st.session_state.messages = []


# Функция рендеринга кнопок
def render_message_with_download(text: str, key_prefix: str = ""):
    pattern = r'\[DOWNLOAD:([^\]]+)\]'
    parts = re.split(pattern, text)

    for i, part in enumerate(parts):
        if i % 2 == 0:
            if part.strip():
                st.markdown(part)
        else:
            filename = part.strip()
            filepath = os.path.join(DOCS_DIR, filename)
            unique_key = f"{key_prefix}download_{filename}_{i}"

            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    file_bytes = f.read()
                st.download_button(
                    label=f"📥 Скачать: {filename}",
                    data=file_bytes,
                    file_name=filename,
                    mime="application/octet-stream",
                    key=unique_key
                )
            else:
                st.warning(f"Файл '{filename}' не найден в папке.")


# ✅ ФУНКЦИЯ ИЗВЛЕЧЕНИЯ ТЕКСТА (ТЕПЕРЬ ОНА СТОИТ ПРАВИЛЬНО - ДО ВЫЗОВА)
def extract_text_from_response(response):
    if hasattr(response, 'messages') and response.messages:
        msg = response.messages[0]
        if hasattr(msg, 'content') and msg.content:
            content_part = msg.content[0]
            if hasattr(content_part, 'text'):
                return content_part.text
            return str(content_part)

    if hasattr(response, 'choices') and response.choices:
        return response.choices[0].message.content
    if hasattr(response, 'message') and response.message:
        return response.message.content

    return str(response)


# Отображение истории
for msg_index, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and "[DOWNLOAD:" in msg["content"]:
            render_message_with_download(msg["content"], key_prefix=f"history_{msg_index}_")
        else:
            st.markdown(msg["content"])

# 5. Обработка ввода пользователя
if user_query := st.chat_input("Например: найди отчет по продажам..."):
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        try:
            search_result = search_file_by_name(user_query)
            prompt_for_ai = f"Пользователь ищет: '{user_query}'. Результат поиска на диске: {search_result}. Сформируй ответ."

            messages_for_api = [
                ChatMessage(role="system", content=SYSTEM_INSTRUCTION)
            ]

            for msg in st.session_state.messages:
                messages_for_api.append(
                    ChatMessage(role=msg["role"], content=msg["content"])
                )

            messages_for_api.append(
                ChatMessage(role="user", content=prompt_for_ai)
            )

            payload = ChatCompletionRequest(
                model="GigaChat-3-Ultra",
                messages=messages_for_api,
                temperature=0.3
            )

            print("📤 Отправляю запрос к GigaChat...")
            response = client.chat.create(payload)

            agent_text = extract_text_from_response(response)
            print(f"✅ Ответ получен: {agent_text[:50]}...")

            render_message_with_download(agent_text, key_prefix="new_")
            st.session_state.messages.append({"role": "assistant", "content": agent_text})

        except Exception as e:
            error_str = str(e)
            print(f"❌ ОШИБКА: {error_str}")
            st.error(f"Ошибка: {e}")