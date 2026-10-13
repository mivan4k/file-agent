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
        admin_password_1 = st.secrets.get("ADMIN_PASSWORD_1", "")
        admin_password_2 = st.secrets.get("ADMIN_PASSWORD_2", "")
        return client_id, client_secret, admin_password_1, admin_password_2
    except (KeyError, FileNotFoundError):
        pass

    load_dotenv(dotenv_path="config.env")
    raw_id = os.getenv("GIGACHAT_CLIENT_ID")
    raw_secret = os.getenv("GIGACHAT_CLIENT_SECRET")

    if not raw_id or not raw_secret:
        return None, None, None, None

    client_id = raw_id.strip().strip("'\"")
    client_secret = raw_secret.strip().strip("'\"")
    admin_password_1 = os.getenv("ADMIN_PASSWORD_1", "")
    admin_password_2 = os.getenv("ADMIN_PASSWORD_2", "")

    return client_id, client_secret, admin_password_1, admin_password_2


client_id, client_secret, admin_password_1, admin_password_2 = get_credentials()

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
        if password_input == admin_password_1 or password_input == admin_password_2:
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
    st.sidebar.header(" Загрузка файлов и архивов")
    st.sidebar.info("Поддерживаются: ZIP, TAR, TAR.GZ, RAR, 7Z, а также обычные файлы")

    uploaded_files = st.sidebar.file_uploader(
        "Выберите файлы или архивы",
        accept_multiple_files=True
    )

    def extract_archive(filepath, extract_dir, depth=0):
        if depth > 3:
            return 0
        
        extracted_count = 0
        filename = os.path.basename(filepath).lower()
        
        try:
            if filename.endswith('.zip'):
                with zipfile.ZipFile(filepath, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                    extracted_count = len(zip_ref.namelist())
                os.remove(filepath)
            
            elif filename.endswith(('.tar', '.tar.gz', '.tgz')):
                with tarfile.open(filepath, 'r:*') as tar_ref:
                    tar_ref.extractall(extract_dir)
                    extracted_count = len(tar_ref.getnames())
                os.remove(filepath)
            
            elif filename.endswith('.rar'):
                try:
                    import rarfile
                    with rarfile.RarFile(filepath, 'r') as rar_ref:
                        rar_ref.extractall(extract_dir)
                        extracted_count = len(rar_ref.namelist())
                    os.remove(filepath)
                except ImportError:
                    st.sidebar.warning("️ Для RAR нужна библиотека rarfile")
                    return 0
            
            elif filename.endswith('.7z'):
                try:
                    import py7zr
                    with py7zr.SevenZipFile(filepath, 'r') as sz_ref:
                        sz_ref.extractall(extract_dir)
                        extracted_count = len(sz_ref.getnames())
                    os.remove(filepath)
                except ImportError:
                    st.sidebar.warning("️ Для 7Z нужна библиотека py7zr")
                    return 0
            
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
            
            with open(temp_path, "wb") as f:
                f.write(file_bytes)
            
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
                size_str = str(len(file_bytes)) + " байт" if len(file_bytes) > 0 else "пустой"
                st.sidebar.success("✅ " + filename + " (" + size_str + ")")

    all_files_recursive = []
    for root, dirs, files in os.walk(DOCS_DIR):
        for f in files:
            rel_path = os.path.relpath(os.path.join(root, f), DOCS_DIR)
            all_files_recursive.append(rel_path)
    
    if all_files_recursive:
        st.sidebar.markdown("** В архиве (" + str(len(all_files_recursive)) + " файлов):**")
        for fname in all_files_recursive:
            full_path = os.path.join(DOCS_DIR, fname)
            fsize = os.path.getsize(full_path)
            size_str = str(fsize) + " байт" if fsize > 0 else "пустой"
            st.sidebar.text("  • " + fname + " (" + size_str + ")")
    else:
        st.sidebar.warning("Архив пуст")

    if st.sidebar.button("🗑️ Очистить архив"):
        for root, dirs, files in os.walk(DOCS_DIR, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except:
                    pass
        st.sidebar.success("Архив очищен!")
        st.rerun()

st.sidebar.markdown("---")


# ============================================================
# НОРМАЛИЗАЦИЯ
# ============================================================
def get_word_variants(word):
    word = word.lower().strip()
    if len(word) < 2:
        return []
    
    variants = [word]
    
    for i in range(1, 5):
        if len(word) - i >= 4:
            stripped = word[:-i]
            if stripped not in variants:
                variants.append(stripped)
    
    return variants


# ============================================================
# РЕКУРСИВНЫЙ ПОИСК
# ============================================================
def search_by_keyword(keyword):
    if not os.path.exists(DOCS_DIR):
        return []
    
    keyword = keyword.lower().strip()
    if len(keyword) < 2:
        return []
    
    variants = get_word_variants(keyword)
    
    matched = []
    for root, dirs, files in os.walk(DOCS_DIR):
        for f in files:
            filename_lower = f.lower()
            for variant in variants:
                if variant in filename_lower:
                    rel_path = os.path.relpath(os.path.join(root, f), DOCS_DIR)
                    if rel_path not in matched:
                        matched.append(rel_path)
                    break
    return matched


def get_all_files_recursive():
    if not os.path.exists(DOCS_DIR):
        return []
    result = []
    for root, dirs, files in os.walk(DOCS_DIR):
        for f in files:
            rel_path = os.path.relpath(os.path.join(root, f), DOCS_DIR)
            result.append(rel_path)
    return result


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
# АНАЛИЗ ЗАПРОСА ИИ (МАКСИМУМ 3 ФРАЗЫ)
# ============================================================
def analyze_query_with_ai(query, files_list):
    files_str = "\n".join(["- " + f for f in files_list]) if files_list else "(архив пуст)"
    
    system_prompt = """Ты — парсер поисковых запросов. Верни СТРОГО JSON-массив из 1-3 ключевых слов для поиска.

ПРАВИЛА:
1. Отбрось служебные слова (привет, найди, покажи, мне, я, хочу, есть, какие).
2. Оставь только слова из запроса пользователя в единственном числе.
3. МАКСИМУМ 3 фразы. НЕ выдумывай синонимы, которых нет в запросе.
4. Добавляй расширения файлов (pptx, xlsx, pdf) только если они ОЧЕВИДНО подразумеваются.
5. Только JSON, без лишнего текста.

ПРИМЕРЫ:
"найди презентации" → ["презентация", "pptx"]
"отчет по продажам" → ["отчет", "продажа"]
"текстовые файлы" → ["текстовый файл", "txt"]
"закон Ньютона" → ["закон", "ньютон"]"""

    user_prompt = "Запрос: '" + query + "'\n\nФайлы в архиве:\n" + files_str + "\n\nВерни JSON (1-3 фразы):"
    
    try:
        response_text = call_gigachat(system_prompt, user_prompt, temperature=0.3)
        
        json_match = re.search(r'\[.*?\]', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            keywords = json.loads(json_str)
            if isinstance(keywords, list) and len(keywords) > 0:
                result = [str(k).strip().lower() for k in keywords if isinstance(k, str) and len(str(k).strip()) >= 2]
                return result[:3]
    except Exception as e:
        print("⚠️ Ошибка парсинга JSON: " + str(e))
    
    stop_words = {"привет", "помоги", "найди", "найти", "покажи", "мне", "я", "хочу", "чтобы", "ты", "есть", "какие", "и", "а", "но", "в", "на", "по"}
    query_clean = re.sub(r'[^\w\s\-_а-яё]', ' ', query.lower())
    words = [w for w in query_clean.split() if len(w) >= 2 and w not in stop_words]
    return words[:3] if words else [query.lower().strip()]


# ============================================================
# УМНЫЙ ПОИСК
# ============================================================
def smart_search(query):
    files_list = get_all_files_recursive()
    
    if not files_list:
        return [], [], "Архив пуст"
    
    debug_info = []
    debug_info.append(" Всего файлов в архиве: " + str(len(files_list)))
    
    search_phrases = analyze_query_with_ai(query, files_list)
    debug_info.append("🤖 ИИ предложил фразы: " + ", ".join(search_phrases))
    
    all_found = []
    for phrase in search_phrases:
        variants = get_word_variants(phrase)
        debug_info.append("🔍 Ищем '" + phrase + "' → варианты: " + ", ".join(variants))
        
        found = search_by_keyword(phrase)
        if found:
            debug_info.append("   ✅ Найдено: " + ", ".join(found))
        else:
            debug_info.append("   ❌ Не найдено")
        
        for f in found:
            if f not in all_found:
                all_found.append(f)
    
    if not all_found:
        debug_info.append("⚠️ Ничего не нашли, делаем fallback-поиск...")
        stop_words = {"привет", "помоги", "найди", "найти", "покажи", "мне", "я", "хочу", "чтобы", "ты", "есть", "какие", "и", "а", "но", "в", "на", "по", "с", "из", "от", "до", "за", "к", "у"}
        query_clean = re.sub(r'[^\w\s\-_а-яё]', ' ', query.lower())
        fallback_words = [w for w in query_clean.split() if len(w) >= 2 and w not in stop_words]
        
        for word in fallback_words:
            variants = get_word_variants(word)
            debug_info.append("  Fallback: ищем '" + word + "' → варианты: " + ", ".join(variants))
            
            found = search_by_keyword(word)
            if found:
                debug_info.append("   ✅ Найдено: " + ", ".join(found))
            
            for f in found:
                if f not in all_found:
                    all_found.append(f)
    
    debug_text = "\n".join(debug_info)
    
    return search_phrases, all_found, debug_text


# ============================================================
# ГЕНЕРАЦИЯ ОТВЕТА
# ============================================================
def generate_final_answer(query, search_phrases, found_files):
    if found_files:
        files_str = "\n".join(["- " + f for f in found_files])
        
        system_prompt = """Ты — дружелюбный ассистент файлового архива.
Отвечай живо, по-человечески, можешь использовать эмодзи.
Кратко опиши, что нашёл."""
        
        user_prompt = "Пользователь спросил: '" + query + "'\n\n"
        user_prompt += "Нашёл " + str(len(found_files)) + " файл(ов):\n" + files_str + "\n\n"
        user_prompt += "Кратко и дружелюбно подтверди находку."
    else:
        system_prompt = """Ты — дружелюбный ассистент файлового архива.
Отвечай живо, по-человечески.
Если ничего не найдено — скажи об этом вежливо."""
        
        user_prompt = "Пользователь спросил: '" + query + "'\n\n"
        user_prompt += "Ничего не нашёл. Вежливо скажи об этом."
    
    return call_gigachat(system_prompt, user_prompt, temperature=0.5)


# ============================================================
# РЕНДЕРИНГ КНОПОК СКАЧИВАНИЯ
# ============================================================
def render_download_buttons(files, prefix=""):
    for idx, filename in enumerate(files):
        filepath = os.path.join(DOCS_DIR, filename)
        key = prefix + "auto_dl_" + filename.replace("/", "_").replace("\\", "_") + "_" + str(idx)

        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                st.download_button(
                    label=" Скачать: " + filename,
                    data=f.read(),
                    file_name=os.path.basename(filename),
                    key=key
                )


# ============================================================
# ИСТОРИЯ
# ============================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ============================================================
# ВВОД ПОЛЬЗОВАТЕЛЯ
# ============================================================
if q := st.chat_input("Например: помоги найти отчёт по продажам..."):
    st.session_state.messages.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)

    with st.chat_message("assistant"):
        try:
            with st.spinner("🔍 Анализирую запрос и ищу файлы..."):
                search_phrases, found_files, debug_text = smart_search(q)
                answer_text = generate_final_answer(q, search_phrases, found_files)
            
            st.markdown(answer_text)

            with st.expander(" Отладка (как работал поиск)"):
                st.code(debug_text, language="text")
                st.markdown("**Все файлы в архиве:**")
                st.markdown("\n".join(["- " + f for f in get_all_files_recursive()]))

            if found_files:
                st.markdown("---")
                st.markdown("**📎 Найдено файлов: " + str(len(found_files)) + "**")
                render_download_buttons(found_files, "new_")

            st.session_state.messages.append({"role": "assistant", "content": answer_text})

        except Exception as e:
            st.error("Ошибка: " + str(e))
            print("❌ ОШИБКА: " + str(e))
