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
st.sidebar.header("🔐 Вход для администратора")

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
            st.sidebar.error("❌ Неверный пароль")
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

    if st.sidebar.button("️ Очистить архив"):
        for f in os.listdir(DOCS_DIR):
            os.remove(os.path.join(DOCS_DIR, f))
        st.sidebar.success("Архив очищен!")
        st.rerun()

st.sidebar.markdown("---")


def get_archive_files_list():
    if not os.path.exists(DOCS_DIR):
        return []
    return [f for f in os.listdir(DOCS_DIR) if os.path.isfile(os.path.join(DOCS_DIR, f))]


def search_file_by_name(query: str) -> str:
    if not os.path.exists(DOCS_DIR):
        return "Архив пуст."

    matched = []
    for root, dirs, files in os.walk(DOCS_DIR):
        for f in files:
            if query.lower() in f.lower():
                matched.append(os.path.relpath(os.path.join(root, f), DOCS_DIR))

    if matched:
        return f"Найдены файлы: {', '.join(matched)}"
    else:
        return "Файлы не найдены."


@st.cache_resource
def get_client():
    return GigaChat(credentials=client_secret, verify_ssl_certs=False)


client = get_client()


def build_system_instruction():
    files_list = get_archive_files_list()

    if files_list:
        files_str = "\n".join(f"- {f}" for f in files_list)
        files_section = f"""
ДОСТУПНЫЕ ФАЙЛЫ В АРХИВЕ (ТОЛЬКО ИХ МОЖНО УПОМИНАТЬ):
{files_str}
"""
    else:
        files_section = """
ВНИМАНИЕ: АРХИВ ПУСТ. Файлов нет. Не упоминай никакие файлы.
"""

    return f"""Ты — ассистент файлового архива.

{files_section}

ПРАВИЛА:
1. Используй маркер [DOWNLOAD:имя_файла] ТОЛЬКО для файлов из списка выше.
2. СТРОГО ЗАПРЕЩЕНО выдумывать файлы, которых нет в списке.
3. Если пользователь ищет файл, которого нет в архиве — честно скажи об этом.
4. Если архив пуст — скажи, что файлов пока нет.
5. Отвечай кратко и по делу.

Пример правильного ответа:
"Вот ваш файл: [DOWNLOAD:report.pdf]"

Пример неправильного ответа (НЕ ДЕЛАЙ ТАК):
"Вот файлы: [DOWNLOAD:отчет_2025.pdf], [DOWNLOAD:презентация.pptx]" — если их нет в списке выше."""


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
            search_result = search_file_by_name(q)
            system_prompt = build_system_instruction()

            user_prompt = f"""Запрос пользователя: '{q}'
Результат локального поиска: {search_result}

Сформируй ответ. Помни: упоминай только файлы из списка доступных!"""

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

            render_message(text, "new_")
            st.session_state.messages.append({"role": "assistant", "content": text})

        except Exception as e:
            st.error(f"Ошибка: {e}")
