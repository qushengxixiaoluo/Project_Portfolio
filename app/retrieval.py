"""BM25 关键词检索（jieba 中文分词），按项目过滤。

检索层做成独立模块，后续可替换为向量检索实现。
"""
import re

import jieba
from rank_bm25 import BM25Okapi

_JIEBA_READY = False


def _ensure_jieba() -> None:
    global _JIEBA_READY
    if not _JIEBA_READY:
        jieba.initialize()
        _JIEBA_READY = True


def _tokenize(text: str) -> list[str]:
    _ensure_jieba()
    words = jieba.lcut(text)
    # 去掉纯标点/空白，保留英文单词与数字
    return [
        w.lower() for w in words
        if w.strip() and not re.fullmatch(r"[^\w]+", w)
    ]


def search(chunks: list[dict], question: str, top_k: int = 8) -> list[dict]:
    """在给定分块中检索与问题最相关的 top_k 块。

    chunks: [{id, filename, content}, ...]
    返回同样的结构，按相关度降序，附 score。
    """
    if not chunks:
        return []
    if len(chunks) <= top_k:
        # 数据量太小没必要建索引，直接返回
        return [{**c, "score": 0.0} for c in chunks[:top_k]]

    tokenized = [_tokenize(c["content"]) for c in chunks]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(_tokenize(question))

    ranked = sorted(
        zip(chunks, scores), key=lambda pair: pair[1], reverse=True
    )[:top_k]
    return [{**c, "score": float(s)} for c, s in ranked if s > 0] or [
        {**c, "score": 0.0} for c, _ in ranked[:3]
    ]
