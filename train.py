"""
Шаг 1: обучение модели для определения мошеннических SMS.

Запуск:  python3 train.py

Какие данные использует (все файлы — в папке проекта, те, что есть):
  spam.csv          — SMS Spam Collection с Kaggle (английский, колонки v1, v2)
  korean_sms.csv    — корейские сообщения   (колонки: label,text)
  kz_sms.csv        — казахстанские (рус/каз) (колонки: label,text)
  extra_*.csv       — любые дополнительные наборы (колонки: label,text)
  feedback.csv      — исправления от пользователей сайта (колонки: label,text)
label = spam или ham (также принимаются 1 / 0).

Результат:
  model.joblib  — обученная модель
  metrics.json  — точность по каждому языку (показывается на сайте)
"""

import glob
import json
import os
import re

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

LABEL_MAP = {"spam": 1, "smishing": 1, "1": 1, "ham": 0, "normal": 0, "0": 0}


def detect_lang(text):
    """Грубое определение языка по алфавиту."""
    if re.search(r"[가-힣]", text):
        return "ko"
    if re.search(r"[әғқңөұүһі]", text.lower()):
        return "kk"
    if re.search(r"[а-яё]", text.lower()):
        return "ru"
    return "en"


def read_simple(path):
    df = pd.read_csv(path, encoding="utf-8")
    return df[["label", "text"]]


def load_data():
    frames = []

    if os.path.exists("spam.csv"):
        df = pd.read_csv("spam.csv", encoding="latin-1")
        df = df[["v1", "v2"]].rename(columns={"v1": "label", "v2": "text"})
        frames.append(df)
        print(f"  spam.csv: {len(df)}")

    files = ["korean_sms.csv", "kz_sms.csv"] + sorted(glob.glob("extra_*.csv")) + ["feedback.csv"]
    for name in files:
        if os.path.exists(name):
            df = read_simple(name)
            frames.append(df)
            print(f"  {name}: {len(df)}")

    if not frames:
        raise FileNotFoundError("Нет данных. Положи spam.csv (и/или korean_sms.csv) в папку проекта.")

    data = pd.concat(frames, ignore_index=True).dropna()
    data["label"] = data["label"].astype(str).str.strip().str.lower().map(LABEL_MAP)
    data["text"] = data["text"].astype(str).str.strip()
    data = data.dropna().drop_duplicates(subset="text")
    data["label"] = data["label"].astype(int)
    data["lang"] = data["text"].apply(detect_lang)
    return data


def build_pipeline():
    # Два вида признаков вместе:
    #  - кусочки символов (char n-grams): хорошо работают для корейского и опечаток
    #  - слова и пары слов (word n-grams): ловят типичные фразы мошенников
    features = FeatureUnion([
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
        ("words", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), token_pattern=r"(?u)\b\w+\b",
                                  sublinear_tf=True)),
    ])
    return Pipeline([
        ("features", features),
        ("clf", LogisticRegression(max_iter=3000, class_weight="balanced")),
    ])


def scores(y_true, y_pred):
    return {
        "n": int(len(y_true)),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 3),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 3),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 3),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 3),
    }


def main():
    print("Загрузка данных:")
    data = load_data()
    print(f"\nВсего сообщений: {len(data)}")
    print(pd.crosstab(data["lang"], data["label"]).rename(columns={0: "нормальные", 1: "мошенничество"}))

    # Делим так, чтобы в тесте были все языки и оба класса в тех же пропорциях
    strat = data["lang"] + "_" + data["label"].astype(str)
    if strat.value_counts().min() < 2:
        strat = data["label"]
    train, test = train_test_split(data, test_size=0.2, random_state=42, stratify=strat)

    # Сообщений на корейском/русском/казахском мало, поэтому даём им больший вес при обучении
    lang_counts = train["lang"].value_counts()
    weights = train["lang"].map(lambda l: min(5.0, lang_counts.max() / lang_counts[l]) if l != "en" else 1.0)

    # Подбираем силу регуляризации C перекрёстной проверкой
    search = GridSearchCV(build_pipeline(), {"clf__C": [1, 4, 10, 30]}, scoring="f1", cv=4, n_jobs=-1)
    search.fit(train["text"], train["label"], clf__sample_weight=weights.values)
    model = search.best_estimator_
    print(f"\nЛучший параметр C = {search.best_params_['clf__C']}")

    pred = model.predict(test["text"])
    metrics = {"overall": scores(test["label"], pred), "by_language": {}}
    print("\n=== Результаты на тестовых данных (модель их не видела) ===")
    print(f"{'язык':6} {'кол-во':>7} {'accuracy':>9} {'precision':>10} {'recall':>7} {'f1':>6}")
    for lang, part in [("ВСЕ", test)] + list(test.groupby("lang")):
        p = model.predict(part["text"])
        s = scores(part["label"], p)
        if lang != "ВСЕ":
            metrics["by_language"][lang] = s
        flag = "" if s["accuracy"] >= 0.8 else "  ← меньше 80%: нужно больше данных"
        print(f"{lang:6} {s['n']:>7} {s['accuracy']:>9.0%} {s['precision']:>10.0%} {s['recall']:>7.0%} {s['f1']:>6.0%}{flag}")

    print("\nМатрица ошибок (строки — правда, столбцы — ответ модели; [нормальное, мошенничество]):")
    print(confusion_matrix(test["label"], pred))

    # Финально дообучаем на ВСЕХ данных, чтобы модель знала как можно больше примеров
    all_counts = data["lang"].value_counts()
    all_w = data["lang"].map(lambda l: min(5.0, all_counts.max() / all_counts[l]) if l != "en" else 1.0)
    model.fit(data["text"], data["label"], clf__sample_weight=all_w.values)

    metrics["train_size"] = int(len(data))
    metrics["languages"] = {k: int(v) for k, v in data["lang"].value_counts().items()}
    joblib.dump(model, "model.joblib")
    with open("metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print("\nМодель сохранена в model.joblib, метрики — в metrics.json")


if __name__ == "__main__":
    main()
