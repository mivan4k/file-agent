import os
import re
import streamlit as st
from dotenv import load_dotenv
from gigachat import GigaChat
from gigachat.models import ChatCompletionRequest, ChatMessage


def get_credentials():
    try:
        client_id = st.secrets["GIGACHAT_CLIENT_ID"]
        client_secret = st.secrets["GIGACHAT_CLIENT_SECRET"]
        admin_password = st.secrets.get("ADMIN_PASSWORD", "")
        return client_id, client_secret, admin_password
    except (KeyError, FileNotFoundError):
        pass

    load_dotenv(dotenv_path="config.env")
    raw_id = os.getenv("GIGACHAT_CLIENT_ID")
    raw_secret = os.getenv("GIGACHAT_CLIENT_SECRET")

    if not raw_id or not raw_secret:
        return None, None, None

    client_id = raw_id.strip().strip("'\"")
    client_secret = raw_secret.strip().strip("'\"")
    admin_password = os.getenv("ADMIN_PASSWORD", "")

    return client_id, client_secret, admin_password


client_id, client_secret, admin_password = get_credentials()

if not client_id or not client_secret:
    st.error("Ошибка: Ключи GigaChat не найдены!")
    st.stop()

st.set_page_config(page_title="ИИ Файловый Менеджер", page_icon="🗂️", layout="wide")
st.title("🗂️ ИИ-Агент для поиска файлов")
st.write("Напишите название файла, и я найду его в архиве.")

DOCS_DIR = "my_documents"
if not os.path.exists(DOCS_DIR):
    os.makedirs(DOCS_DIR)

st.sidebar.markdown("---")
st.sidebar.header(" Вход для администратора")

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

if not st.session_state.is_admin:
    password_input = st.sidebar.text_input("Введите пароль администратора:", type="password")

    if st.sidebar.button("Войти"):
        if password_input == admin_password:
            st.session_state.is_admin = True
            st.sidebar.success("✅ Вход выполнен!")
            st.rerun()
        else:
            st.sidebar.error(" Неверный пароль")
else:
    st.sidebar.success("✅ Вы вошли как администратор")

    if st.sidebar.button("🚪 Выйти"):
        st.session_state.is_admin = False
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.header("📤 Загрузка файлов в архив")

    uploaded_files = st.sidebar.file_uploader(
        "Выберите файлы",
        accept_multiple_files=True,
        type=["pdf", "txt", "doc", "docx", "xls", "xlsx", "jpg", "png", "zip", "rar", "pptx", "csv"]
    )

    if uploaded_files:
        for uploaded_file in uploaded_files:
            filepath = os.path.join(DOCS_DIR, uploaded_file.name)
            if not os.path.exists(filepath):
                with open(filepath, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.sidebar.success(f"✅ {uploaded_file.name}")
            else:
                st.sidebar.info(f"⚠️ {uploaded_file.name} уже есть")

    files_in_archive = [f for f in os.listdir(DOCS_DIR) if os.path.isfile(os.path.join(DOCS_DIR, f))]
    if files_in_archive:
        st.sidebar.markdown(f"**📁 В архиве ({len(files_in_archive)}):**")
        for fname in files_in_archive:
            st.sidebar.text(f"  • {fname}")
    else:
        st.sidebar.warning("Архив пуст")

    if st.sidebar.button("🗑️ Очистить архив"):
        for f in os.listdir(DOCS_DIR):
            os.remove(os.path.join(DOCS_DIR, f))
        st.sidebar.success("Архив очищен!")
        st.rerun()

st.sidebar.markdown("---")


def get_archive_files_list():
    if not os.path.exists(DOCS_DIR):
        return []
    return [f for f in os.listdir(DOCS_DIR) if os.path.isfile(os.path.join(DOCS_DIR, f))]


def search_file_by_name(query: str) -> list:
    if not os.path.exists(DOCS_DIR):
        return []
    
    matched = []
    for root, dirs, files in os.walk(DOCS_DIR):
        for f in files:
            if query.lower() in f.lower():
                matched.append(os.path.relpath(os.path.join(root, f), DOCS_DIR))
    
    return matched


@st.cache_resource
def get_client():
    return GigaChat(credentials=client_secret, verify_ssl_certs=False)


client = get_client()


def build_system_instruction():
    files_list = get_archive_files_list()

    if files_list:
        files_str = "\n".join(f"- {f}" for f in files_list)
        files_section = f"""
ДОСТУПНЫЕ ФАЙЛЫ В АРХИВЕ:
{files_str}
"""
    else:
        files_section = """
ВНИМАНИЕ: АРХИВ ПУСТ. Файлов нет.
"""

    return f"""Ты — ассистент файлового архива.

{files_section}

ПРАВИЛА:
1. Отвечай кратко и по делу.
2. Если файлы найдены — просто подтверди это текстом.
3. Если файлов нет — скажи, что ничего не найдено.
4. НЕ используй маркеры [DOWNLOAD:...] — кнопки создаются автоматически.

Пример ответа при найденных файлах:
"Нашёл для вас следующие файлы:"

Пример ответа при отсутствии файлов:
"По вашему запросу ничего не найдено в архиве.""""


if "messages" not in st.session_state:
    st.session_state.messages = []


def render_message(text: str, prefix: str = ""):
    parts = re.split(r'\[DOWNLOAD:([^\]]+)\]', text)

    for i, part in enumerate(parts):
        if i % 2 == 0:
            if part.strip():
                st.markdown(part)
        else:
            filename = part.strip()
            filepath = os.path.join(DOCS_DIR, filename)
            key = f"{prefix}dl_{filename}_{i}"

            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    st.download_button(
                        label=f"📥 Скачать: {filename}",
                        data=f.read(),
                        file_name=filename,
                        key=key
                    )


def extract_text(response):
    if hasattr(response, 'messages') and response.messages:
        c = response.messages[0].content
        if c and hasattr(c[0], 'text'):
            return c[0].text
    if hasattr(response, 'choices') and response.choices:
        return response.choices[0].message.content
    return str(response)


def render_download_buttons(files: list, prefix: str = ""):
    for idx, filename in enumerate(files):
        filepath = os.path.join(DOCS_DIR, filename)
        key = f"{prefix}auto_dl_{filename}_{idx}"
        
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                st.download_button(
                    label=f"📥 Скачать: {filename}",
                    data=f.read(),
                    file_name=filename,
                    key=key
                )


for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and "[DOWNLOAD:" in msg["content"]:
            render_message(msg["content"], f"hist{idx}_")
        else:
            st.markdown(msg["content"])


if q := st.chat_input("Например: найди отчёт по продажам..."):
    st.session_state.messages.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)

    with st.chat_message("assistant"):
        try:
            found_files = search_file_by_name(q)
            system_prompt = build_system_instruction()

            if found_files:
                files_str = "\n".join(f"- {f}" for f in found_files)
                user_prompt = f"""Запрос пользователя: '{q}'
Найдено файлов: {len(found_files)}
{files_str}

Подтверди находку текстом."""
            else:
                user_prompt = f"""Запрос пользователя: '{q}'
Файлы не найдены.

Скажи, что ничего не найдено."""

            msgs = [ChatMessage(role="system", content=system_prompt)]
            for m in st.session_state.messages:
                msgs.append(ChatMessage(role=m["role"], content=m["content"]))
            msgs.append(ChatMessage(role="user", content=user_prompt))

            payload = ChatCompletionRequest(
                model="GigaChat-3-Ultra",
                messages=msgs,
                temperature=0.3
            )

            response = client.chat.create(payload)
            text = extract_text(response)

            st.markdown(text)
            
            if found_files:
                st.markdown("---")
                st.markdown(f"**📎 Найдено файлов: {len(found_files)}**")
                render_download_buttons(found_files, "new_")
            
            st.session_state.messages.append({"role": "assistant", "content": text})

        except Exception as e:
            st.error(f"Ошибка: {e}")
