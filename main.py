import os
import re
import zipfile
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
st.write("Напишите, что ищете — я пойму любую фразу.")

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
        "Выберите файлы или архивы (zip)",
        accept_multiple_files=True,
        type=["pdf", "txt", "doc", "docx", "xls", "xlsx", "jpg", "png", "zip", "rar", "pptx", "csv"]
    )

    if uploaded_files:
        for uploaded_file in uploaded_files:
            filename = uploaded_file.name

            if filename.lower().endswith('.zip'):
                try:
                    temp_path = os.path.join(DOCS_DIR, filename)
                    with open(temp_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    with zipfile.ZipFile(temp_path, 'r') as zip_ref:
                        zip_ref.extractall(DOCS_DIR)
                    os.remove(temp_path)
                    extracted = zip_ref.namelist()
                    st.sidebar.success("✅ Распакован " + filename + " (" + str(len(extracted)) + " файлов)")
                except Exception as e:
                    st.sidebar.error("❌ Ошибка распаковки " + filename + ": " + str(e))
            else:
                filepath = os.path.join(DOCS_DIR, filename)
                if not os.path.exists(filepath):
                    with open(filepath, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    st.sidebar.success("✅ " + filename)
                else:
                    st.sidebar.info("️ " + filename + " уже есть")

    files_in_archive = [f for f in os.listdir(DOCS_DIR) if os.path.isfile(os.path.join(DOCS_DIR, f))]
    if files_in_archive:
        st.sidebar.markdown("**📁 В архиве (" + str(len(files_in_archive)) + "):**")
        for fname in files_in_archive:
            st.sidebar.text("  • " + fname)
    else:
        st.sidebar.warning("Архив пуст")

    if st.sidebar.button("🗑️ Очистить архив"):
        for f in os.listdir(DOCS_DIR):
            fp = os.path.join(DOCS_DIR, f)
            if os.path.isfile(fp):
                os.remove(fp)
        st.sidebar.success("Архив очищен!")
        st.rerun()

st.sidebar.markdown("---")


STOP_WORDS = {
    "помоги", "помогите", "найди", "найти", "покажи", "покажите",
    "открой", "открыть", "скачай", "скачать", "давай", "дайте",
    "посмотри", "посмотрите", "подскажи", "подскажите", "достань",
    "вытащи", "извлеки", "предоставь", "предоставьте", "выдай",
    "выдайте", "поищи", "поискать", "ищи", "искать", "отыщи",
    "я", "мы", "ты", "вы", "он", "она", "оно", "они",
    "мне", "нам", "тебе", "вам", "ему", "ей", "им",
    "меня", "нас", "тебя", "вас", "его", "её", "их",
    "мой", "моя", "моё", "мои", "наш", "наша", "наше", "наши",
    "твой", "твоя", "твоё", "твои", "ваш", "ваша", "ваше", "ваши",
    "чтобы", "что", "и", "а", "но", "или", "же", "бы", "ли",
    "в", "на", "по", "с", "из", "от", "до", "за", "к", "у",
    "о", "об", "обо", "при", "через", "после", "перед", "между",
    "для", "без", "кроме", "вместо", "около", "возле", "рядом",
    "пожалуйста", "будь", "будьте", "добр", "хороший",
    "хочу", "хотел", "хотела", "хотелось", "нужно", "надо",
    "необходимо", "требуется", "желательно", "мечтаю",
    "себя", "сам", "сама",
    "только", "именно", "даже", "уже", "ещё", "еще",
    "вот", "вон", "тут", "там", "здесь", "сейчас", "потом",
    "быстро", "срочно", "ладно", "ок", "окей",
    "где", "как", "когда", "почему", "зачем", "какой", "какая",
    "какое", "какие", "кто", "сколько", "есть",
    "файл", "файлы", "файлик", "документ", "документы", "документик",
    "бумажка", "бумажки", "материал", "материалы", "вещь", "вещи",
    "всё", "все", "любой", "любое", "любая", "любые", "что-нибудь",
    "что-либо", "ничего", "нечто", "кое-что",
    "просто", "нужен", "нужна", "нужно", "хотелось", "желательно"
}


def extract_keywords(query):
    query = query.lower()
    query = re.sub(r'[^\w\s\-_а-яё]', ' ', query)
    words = query.split()
    keywords = []
    for word in words:
        word_clean = word.strip()
        if len(word_clean) < 2:
            continue
        if word_clean in STOP_WORDS:
            continue
        if word_clean not in keywords:
            keywords.append(word_clean)
    return keywords


def search_file_by_name(query):
    if not os.path.exists(DOCS_DIR):
        return []

    keywords = extract_keywords(query)

    if not keywords:
        keywords = [query.lower().strip()]

    matched = []
    for root, dirs, files in os.walk(DOCS_DIR):
        for f in files:
            filename_lower = f.lower()
            if all(kw in filename_lower for kw in keywords):
                rel_path = os.path.relpath(os.path.join(root, f), DOCS_DIR)
                if rel_path not in matched:
                    matched.append(rel_path)

    if not matched and len(keywords) > 1:
        for root, dirs, files in os.walk(DOCS_DIR):
            for f in files:
                filename_lower = f.lower()
                if any(kw in filename_lower for kw in keywords):
                    rel_path = os.path.relpath(os.path.join(root, f), DOCS_DIR)
                    if rel_path not in matched:
                        matched.append(rel_path)

    return matched


def get_archive_files_list():
    if not os.path.exists(DOCS_DIR):
        return []
    return [f for f in os.listdir(DOCS_DIR) if os.path.isfile(os.path.join(DOCS_DIR, f))]


@st.cache_resource
def get_client():
    return GigaChat(credentials=client_secret, verify_ssl_certs=False)


client = get_client()


def build_system_instruction():
    files_list = get_archive_files_list()

    if files_list:
        files_str = "\n".join(["- " + f for f in files_list])
        files_section = "ДОСТУПНЫЕ ФАЙЛЫ В АРХИВЕ:\n" + files_str + "\n"
    else:
        files_section = "ВНИМАНИЕ: АРХИВ ПУСТ. Файлов нет.\n"

    instruction = "Ты — дружелюбный ассистент файлового архива.\n\n"
    instruction += files_section + "\n"
    instruction += "ПРАВИЛА:\n"
    instruction += "1. Отвечай живо и по-человечески, как хороший помощник.\n"
    instruction += "2. Если файлы найдены — кратко опиши, что нашёл.\n"
    instruction += "3. Если файлов нет — скажи об этом вежливо и предложи уточнить запрос.\n"
    instruction += "4. НЕ используй маркеры [DOWNLOAD:...] — кнопки создаются автоматически.\n"
    instruction += "5. Можешь использовать эмодзи для живости.\n"

    return instruction


if "messages" not in st.session_state:
    st.session_state.messages = []


def extract_text(response):
    if hasattr(response, 'messages') and response.messages:
        c = response.messages[0].content
        if c and hasattr(c[0], 'text'):
            return c[0].text
    if hasattr(response, 'choices') and response.choices:
        return response.choices[0].message.content
    return str(response)


def render_download_buttons(files, prefix=""):
    for idx, filename in enumerate(files):
        filepath = os.path.join(DOCS_DIR, filename)
        key = prefix + "auto_dl_" + filename + "_" + str(idx)

        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                st.download_button(
                    label=" Скачать: " + filename,
                    data=f.read(),
                    file_name=filename,
                    key=key
                )


for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


if q := st.chat_input("Например: помоги найти отчёт по продажам..."):
    st.session_state.messages.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)

    with st.chat_message("assistant"):
        try:
            found_files = search_file_by_name(q)
            keywords = extract_keywords(q)
            system_prompt = build_system_instruction()

            if found_files:
                files_str = "\n".join(["- " + f for f in found_files])
                user_prompt = "Запрос пользователя: '" + q + "'\n"
                user_prompt += "Ключевые слова для поиска: " + ", ".join(keywords) + "\n"
                user_prompt += "Найдено файлов: " + str(len(found_files)) + "\n"
                user_prompt += files_str + "\n\n"
                user_prompt += "Кратко и дружелюбно подтверди, что нашёл эти файлы."
            else:
                user_prompt = "Запрос пользователя: '" + q + "'\n"
                user_prompt += "Ключевые слова: " + ", ".join(keywords) + "\n"
                user_prompt += "Файлы не найдены.\n\n"
                user_prompt += "Вежливо скажи, что ничего не нашёл, и предложи уточнить запрос."

            msgs = [ChatMessage(role="system", content=system_prompt)]
            for m in st.session_state.messages:
                msgs.append(ChatMessage(role=m["role"], content=m["content"]))
            msgs.append(ChatMessage(role="user", content=user_prompt))

            payload = ChatCompletionRequest(
                model="GigaChat-3-Ultra",
                messages=msgs,
                temperature=0.5
            )

            response = client.chat.create(payload)
            text = extract_text(response)

            st.markdown(text)

            if found_files:
                st.markdown("---")
                st.markdown("**📎 Найдено файлов: " + str(len(found_files)) + "**")
                render_download_buttons(found_files, "new_")

            st.session_state.messages.append({"role": "assistant", "content": text})

        except Exception as e:
            st.error("Ошибка: " + str(e))
