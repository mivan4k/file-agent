import os
import re
import json
import zipfile
import tarfile
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
st.write("Загрузите архив или файлы — я всё найду!")

DOCS_DIR = "my_documents"
if not os.path.exists(DOCS_DIR):
    os.makedirs(DOCS_DIR)


# ============================================================
# АДМИН-ПАНЕЛЬ
# ============================================================
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
    st.sidebar.header("📤 Загрузка файлов и архивов")
    st.sidebar.info("Поддерживаются: ZIP, TAR, TAR.GZ, RAR, 7Z, а также обычные файлы")

    uploaded_files = st.sidebar.file_uploader(
        "Выберите файлы или архивы",
        accept_multiple_files=True
    )

    def extract_archive(filepath, extract_dir, depth=0):
        """Рекурсивная распаковка архивов."""
        if depth > 3:  # Максимальная глубина вложенности
            return 0
        
        extracted_count = 0
        filename = os.path.basename(filepath).lower()
        
        try:
            # ZIP
            if filename.endswith('.zip'):
                with zipfile.ZipFile(filepath, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                    extracted_count = len(zip_ref.namelist())
                os.remove(filepath)
            
            # TAR, TAR.GZ, TGZ
            elif filename.endswith(('.tar', '.tar.gz', '.tgz')):
                with tarfile.open(filepath, 'r:*') as tar_ref:
                    tar_ref.extractall(extract_dir)
                    extracted_count = len(tar_ref.getnames())
                os.remove(filepath)
            
            # RAR
            elif filename.endswith('.rar'):
                try:
                    import rarfile
                    with rarfile.RarFile(filepath, 'r') as rar_ref:
                        rar_ref.extractall(extract_dir)
                        extracted_count = len(rar_ref.namelist())
                    os.remove(filepath)
                except ImportError:
                    st.sidebar.warning("⚠️ Для RAR нужна библиотека rarfile")
                    return 0
            
            # 7Z
            elif filename.endswith('.7z'):
                try:
                    import py7zr
                    with py7zr.SevenZipFile(filepath, 'r') as sz_ref:
                        sz_ref.extractall(extract_dir)
                        extracted_count = len(sz_ref.getnames())
                    os.remove(filepath)
                except ImportError:
                    st.sidebar.warning("⚠️ Для 7Z нужна библиотека py7zr")
                    return 0
            
            # Рекурсивная распаковка вложенных архивов
            if extracted_count > 0:
                for item in os.listdir(extract_dir):
                    item_path = os.path.join(extract_dir, item)
                    if os.path.isfile(item_path):
                        sub_count = extract_archive(item_path, extract_dir, depth + 1)
                        extracted_count += sub_count
        
        except Exception as e:
            st.sidebar.error("❌ Ошибка распаковки " + os.path.basename(filepath) + ": " + str(e))
        
        return extracted_count

    if uploaded_files:
        for uploaded_file in uploaded_files:
            filename = uploaded_file.name
            file_bytes = uploaded_file.getvalue()
            temp_path = os.path.join(DOCS_DIR, filename)
            
            # Сохраняем файл временно
            with open(temp_path, "wb") as f:
                f.write(file_bytes)
            
            # Проверяем, архив ли это
            is_archive = False
            archive_extensions = ['.zip', '.tar', '.tar.gz', '.tgz', '.rar', '.7z']
            
            for ext in archive_extensions:
                if filename.lower().endswith(ext):
                    is_archive = True
                    break
            
            if is_archive:
                extracted = extract_archive(temp_path, DOCS_DIR)
                if extracted > 0:
                    st.sidebar.success("✅ Распакован " + filename + " (" + str(extracted) + " файлов)")
                else:
                    st.sidebar.warning("⚠️ " + filename + " не удалось распаковать")
            else:
                # Обычный файл — оставляем как есть
                size_str = str(len(file_bytes)) + " байт" if len(file_bytes) > 0 else "пустой"
                st.sidebar.success("✅ " + filename + " (" + size_str + ")")

    files_in_archive = [f for f in os.listdir(DOCS_DIR) if os.path.isfile(os.path.join(DOCS_DIR, f))]
    if files_in_archive:
        st.sidebar.markdown("** В архиве (" + str(len(files_in_archive)) + "):**")
        for fname in files_in_archive:
            fsize = os.path.getsize(os.path.join(DOCS_DIR, fname))
            size_str = str(fsize) + " байт" if fsize > 0 else "пустой"
            st.sidebar.text("  • " + fname + " (" + size_str + ")")
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


# ============================================================
# ПОИСК ПО ИМЕНИ ФАЙЛА
# ============================================================
def search_by_keyword(keyword):
    """Ищет файлы, содержащие ключевое слово в названии."""
    if not os.path.exists(DOCS_DIR):
        return []
    
    keyword = keyword.lower().strip()
    if len(keyword) < 2:
        return []
    
    matched = []
    for root, dirs, files in os.walk(DOCS_DIR):
        for f in files:
            if keyword in f.lower():
                rel_path = os.path.relpath(os.path.join(root, f), DOCS_DIR)
                if rel_path not in matched:
                    matched.append(rel_path)
    return matched


def search_all_files():
    """Возвращает все файлы в архиве."""
    if not os.path.exists(DOCS_DIR):
        return []
    return [f for f in os.listdir(DOCS_DIR) if os.path.isfile(os.path.join(DOCS_DIR, f))]


def get_archive_files_list():
    return search_all_files()


# ============================================================
# КЛИЕНТ GIGACHAT
# ============================================================
@st.cache_resource
def get_client():
    return GigaChat(credentials=client_secret, verify_ssl_certs=False)


client = get_client()


def extract_text(response):
    if hasattr(response, 'messages') and response.messages:
        c = response.messages[0].content
        if c and hasattr(c[0], 'text'):
            return c[0].text
    if hasattr(response, 'choices') and response.choices:
        return response.choices[0].message.content
    return str(response)


def call_gigachat(system_prompt, user_prompt, temperature=0.3):
    """Универсальная функция вызова GigaChat."""
    msgs = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt)
    ]
    
    payload = ChatCompletionRequest(
        model="GigaChat-3-Ultra",
        messages=msgs,
        temperature=temperature
    )
    
    response = client.chat.create(payload)
    
    return extract_text(response)


# ============================================================
# ШАГ 1: АНАЛИЗ ЗАПРОСА ИИ-ОЙ
# ============================================================
def analyze_query_with_ai(query, files_list):
    files_str = "\n".join(["- " + f for f in files_list]) if files_list else "(архив пуст)"
    
    system_prompt = """Ты — аналитик поисковых запросов для файлового архива.
Твоя задача: проанализировать запрос пользователя и предложить СПИСОК поисковых фраз (ключевых слов), 
по которым нужно искать файлы в архиве.

ПРАВИЛА:
1. Верни ТОЛЬКО JSON-массив строк. Никакого другого текста.
2. Предложи от 2 до 5 поисковых фраз.
3. Включи:
   - Прямые слова из запроса
   - Синонимы и похожие слова
   - Возможные опечатки или варианты написания
   - Типы файлов (расширения), если уместно
4. Все фразы — в нижнем регистре.
5. Каждая фраза — короткая (1-2 слова).

ПРИМЕРЫ:
Запрос: "Какие есть презентации?"
Ответ: ["презентация", "презентации", "pptx", "слайды", "доклад"]

Запрос: "найди отчет по продажам за 2024"
Ответ: ["отчет", "отчёт", "продажи", "2024", "xlsx", "csv"]

Запрос: "документ про закон Ньютона"
Ответ: ["закон", "ньютон", "физика", "документ", "docx", "pdf"]"""

    user_prompt = "Запрос пользователя: '" + query + "'\n\nФайлы в архиве:\n" + files_str + "\n\nВерни JSON-массив поисковых фраз:"
    
    try:
        response_text = call_gigachat(system_prompt, user_prompt, temperature=0.3)
        
        json_match = re.search(r'\[.*?\]', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            keywords = json.loads(json_str)
            if isinstance(keywords, list) and len(keywords) > 0:
                return [str(k).strip().lower() for k in keywords if isinstance(k, str) and len(str(k).strip()) >= 2]
    except Exception as e:
        print("⚠️ Ошибка парсинга JSON от ИИ: " + str(e))
    
    query_clean = re.sub(r'[^\w\s\-_а-яё]', ' ', query.lower())
    words = [w for w in query_clean.split() if len(w) >= 2]
    return words[:5] if words else [query.lower().strip()]


# ============================================================
# ШАГ 2: УМНЫЙ ПОИСК
# ============================================================
def smart_search(query):
    files_list = get_archive_files_list()
    
    if not files_list:
        return [], []
    
    search_phrases = analyze_query_with_ai(query, files_list)
    
    all_found = []
    for phrase in search_phrases:
        found = search_by_keyword(phrase)
        for f in found:
            if f not in all_found:
                all_found.append(f)
    
    return search_phrases, all_found


# ============================================================
# ШАГ 3: ГЕНЕРАЦИЯ ФИНАЛЬНОГО ОТВЕТА
# ============================================================
def generate_final_answer(query, search_phrases, found_files, all_files):
    if found_files:
        files_str = "\n".join(["- " + f for f in found_files])
        phrases_str = ", ".join(search_phrases)
        
        system_prompt = """Ты — дружелюбный ассистент файлового архива.
Отвечай живо, по-человечески, можешь использовать эмодзи.
Кратко опиши, что нашёл."""
        
        user_prompt = "Пользователь спросил: '" + query + "'\n\n"
        user_prompt += "Я искал по фразам: " + phrases_str + "\n"
        user_prompt += "Нашёл " + str(len(found_files)) + " файл(ов):\n" + files_str + "\n\n"
        user_prompt += "Кратко и дружелюбно подтверди находку."
    else:
        system_prompt = """Ты — дружелюбный ассистент файлового архива.
Отвечай живо, по-человечески, можешь использовать эмодзи.
Если ничего не найдено — скажи об этом вежливо и предложи уточнить запрос."""
        
        user_prompt = "Пользователь спросил: '" + query + "'\n\n"
        user_prompt += "Я искал по фразам: " + ", ".join(search_phrases) + "\n"
        user_prompt += "Но ничего не нашёл в архиве.\n\n"
        user_prompt += "Вежливо скажи, что ничего не найдено, и предложи уточнить запрос."
    
    return call_gigachat(system_prompt, user_prompt, temperature=0.5)


# ============================================================
# РЕНДЕРИНГ КНОПОК СКАЧИВАНИЯ
# ============================================================
def render_download_buttons(files, prefix=""):
    for idx, filename in enumerate(files):
        filepath = os.path.join(DOCS_DIR, filename)
        key = prefix + "auto_dl_" + filename + "_" + str(idx)

        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                st.download_button(
                    label="📥 Скачать: " + filename,
                    data=f.read(),
                    file_name=filename,
                    key=key
                )


# ============================================================
# ОТОБРАЖЕНИЕ ИСТОРИИ
# ============================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ============================================================
# ОБРАБОТКА ВВОДА ПОЛЬЗОВАТЕЛЯ
# ============================================================
if q := st.chat_input("Например: помоги найти отчёт по продажам..."):
    st.session_state.messages.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)

    with st.chat_message("assistant"):
        try:
            with st.spinner("🔍 Анализирую запрос и ищу файлы..."):
                search_phrases, found_files = smart_search(q)
                all_files = get_archive_files_list()
                answer_text = generate_final_answer(q, search_phrases, found_files, all_files)
            
            st.markdown(answer_text)

            if found_files:
                st.markdown("---")
                st.markdown("**📎 Найдено файлов: " + str(len(found_files)) + "**")
                render_download_buttons(found_files, "new_")

            st.session_state.messages.append({"role": "assistant", "content": answer_text})

        except Exception as e:
            st.error("Ошибка: " + str(e))
            print("❌ ОШИБКА: " + str(e))
