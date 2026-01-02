import json
import re
import pdfplumber

def is_bold(font_name):
    """Перевіряє, чи шрифт жирний"""
    if not font_name: return False
    name = font_name.lower()
    return "bold" in name or "bld" in name or "black" in name or "heavy" in name

def clean_text(text):
    """Видаляє зайві пробіли"""
    return re.sub(r'\s+', ' ', text).strip()

def parse_pdf(filename):
    questions = []
    print(f"Обробляю файл: {filename}")
    
    with pdfplumber.open(filename) as pdf:
        raw_lines = []
        
        # --- ПРОХІД ПО ВСІХ СТОРІНКАХ ---
        for i, page in enumerate(pdf.pages):
            width = page.width
            height = page.height
            
            # Мінімальна обрізка (10 пікселів), щоб прибрати технічні поля,
            # але не зачепити текст питань.
            try:
                cropped = page.crop((0, 10, width, height - 10))
            except:
                cropped = page

            # Витягуємо слова
            words = cropped.extract_words(keep_blank_chars=True, extra_attrs=["fontname"])
            if not words: continue
            
            # Сортуємо слова (рядок за рядком)
            words.sort(key=lambda w: (int(w['top']), w['x0']))
            
            line_buffer = []
            if not words: continue
            
            last_top = words[0]['top']
            has_bold_in_line = False
            
            # Збираємо слова в рядки
            for w in words:
                # Якщо нове слово нижче попереднього більше ніж на 5 пікселів -> це новий рядок
                if abs(w['top'] - last_top) > 5:
                    text_str = " ".join([wb['text'] for wb in line_buffer])
                    
                    if text_str.strip():
                        raw_lines.append({"text": text_str, "has_bold": has_bold_in_line})
                    
                    # Скидаємо буфер
                    line_buffer = []
                    has_bold_in_line = False
                    last_top = w['top']
                
                line_buffer.append(w)
                if is_bold(w['fontname']):
                    has_bold_in_line = True
            
            # Додаємо останній рядок сторінки
            if line_buffer:
                text_str = " ".join([wb['text'] for wb in line_buffer])
                if text_str.strip():
                    raw_lines.append({"text": text_str, "has_bold": has_bold_in_line})

    print(f"Зчитано {len(raw_lines)} рядків. Аналізую...")

    # --- ЛОГІКА РОЗПІЗНАВАННЯ (REGEX) ---
    current_q = None
    
    # 1. Регулярка для варіантів (А., В., С., D., E.) - Кирилиця та Латиниця
    # Початок рядка -> Можливі пробіли -> Літера -> Крапка або Дужка
    opt_pattern = re.compile(r'^\s*([A-EА-Еa-e])[\.\)]\s*(.*)', re.IGNORECASE)
    
    # 2. Регулярка для питань (1., 24.)
    # Початок рядка -> Цифри -> Крапка
    q_pattern = re.compile(r'^\s*(\d+)\.\s*(.*)')

    for line_data in raw_lines:
        text = clean_text(line_data["text"])
        is_bold_line = line_data["has_bold"]
        
        if not text: continue

        # --- КРОК 1: ЧИ ЦЕ ВАРІАНТ ВІДПОВІДІ? ---
        match_opt = opt_pattern.match(text)
        
        # Це варіант, ТІЛЬКИ якщо у нас вже відкрито питання
        if match_opt and current_q:
            opt_text = match_opt.group(2).strip()
            # Якщо текст пустий (рядок був просто "А."), то беремо все крім перших символів
            if not opt_text: 
                # Видаляємо перші 3 символи ("А. ") грубо
                opt_text = text[2:].strip() if len(text) > 2 else ""

            current_q["opts"].append(opt_text)
            
            # Якщо в цьому рядку був жирний шрифт -> це правильна відповідь
            if is_bold_line:
                current_q["c"] = len(current_q["opts"]) - 1
            continue

        # --- КРОК 2: ЧИ ЦЕ НОВЕ ПИТАННЯ? ---
        match_q = q_pattern.match(text)
        
        if match_q:
            # Закриваємо попереднє питання
            if current_q:
                # Валідація: зберігаємо тільки якщо є варіанти відповідей
                if current_q['opts']:
                    if current_q['c'] == -1: current_q['c'] = 0 # Страховка
                    questions.append(current_q)
            
            # Створюємо нове
            current_q = {
                "id": int(match_q.group(1)),
                "q": match_q.group(2).strip(),
                "opts": [],
                "c": -1
            }
            continue
        
        # --- КРОК 3: ПРОДОВЖЕННЯ ТЕКСТУ ---
        if current_q:
            # Якщо ми вже почали записувати варіанти (масив не пустий),
            # то цей рядок - продовження останнього варіанту
            if current_q["opts"]:
                current_q["opts"][-1] += " " + text
            else:
                # Якщо варіантів ще немає, то цей рядок - продовження питання
                current_q["q"] += " " + text

    # Додаємо останнє питання
    if current_q and current_q['opts']:
        if current_q['c'] == -1: current_q['c'] = 0
        questions.append(current_q)

    return questions

if __name__ == "__main__":
    try:
        data = parse_pdf('base.pdf')
        print(f"Успішно знайдено {len(data)} питань.")
        
        with open('questions.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Помилка: {e}")
        # Створюємо пустий файл, щоб Github Actions не впав червоним
        with open('questions.json', 'w', encoding='utf-8') as f:
            json.dump([], f)
