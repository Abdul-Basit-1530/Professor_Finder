"""Bilingual research-field taxonomy and deterministic field matching.

Chinese and English terminology map to the same canonical field, e.g.
"自然语言处理", "NLP" and "natural language processing" -> Natural Language Processing.
Matching returns the exact keywords that matched so every "match" shown to the
user is backed by evidence from the source text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class FieldSpec:
    key: str
    label: str
    label_zh: str | None = None
    en: list[str] = field(default_factory=list)
    zh: list[str] = field(default_factory=list)
    acronyms: list[str] = field(default_factory=list)  # case-sensitive, word-bounded
    custom: bool = False

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "label_zh": self.label_zh, "custom": self.custom}


TAXONOMY: list[FieldSpec] = [
    FieldSpec("computer_science", "Computer Science", "计算机科学",
              ["computer science", "computing", "computer and information science", "theory of computation",
               "algorithm", "algorithms"],
              ["计算机科学", "计算机", "计算科学", "算法"]),
    FieldSpec("artificial_intelligence", "Artificial Intelligence", "人工智能",
              ["artificial intelligence", "intelligent systems", "knowledge representation", "automated reasoning",
               "multi-agent", "intelligent agents", "large language model", "foundation model", "generative ai"],
              ["人工智能", "智能系统", "知识图谱", "智能体", "大模型", "大语言模型", "生成式"],
              ["AI", "AGI", "LLM", "LLMs"]),
    FieldSpec("machine_learning", "Machine Learning", "机器学习",
              ["machine learning", "deep learning", "neural network", "reinforcement learning",
               "statistical learning", "representation learning", "federated learning", "pattern recognition",
               "transfer learning", "graph neural network"],
              ["机器学习", "深度学习", "神经网络", "强化学习", "模式识别", "联邦学习", "统计学习", "表示学习"],
              ["ML", "GNN", "GNNs"]),
    FieldSpec("information_technology", "Information Technology", "信息技术",
              ["information technology", "information systems", "information management", "information science"],
              ["信息技术", "信息系统", "信息管理", "信息科学", "信息工程"],
              ["IT"]),
    FieldSpec("software_engineering", "Software Engineering", "软件工程",
              ["software engineering", "software testing", "program analysis", "software development",
               "formal methods", "program verification", "software architecture", "programming languages",
               "compiler", "compilers"],
              ["软件工程", "软件测试", "程序分析", "软件开发", "形式化方法", "程序验证", "软件体系结构", "编译", "程序设计语言"]),
    FieldSpec("data_science", "Data Science", "数据科学",
              ["data science", "data mining", "big data", "data analytics", "data management", "databases",
               "database", "knowledge discovery", "recommender system", "recommendation system"],
              ["数据科学", "数据挖掘", "大数据", "数据分析", "数据管理", "数据库", "推荐系统"]),
    FieldSpec("computer_engineering", "Computer Engineering", "计算机工程",
              ["computer engineering", "computer architecture", "embedded systems", "embedded system",
               "high performance computing", "parallel computing", "hardware", "vlsi", "integrated circuit",
               "processor design"],
              ["计算机工程", "计算机体系结构", "计算机系统结构", "嵌入式", "高性能计算", "并行计算", "集成电路", "芯片", "处理器"],
              ["HPC", "FPGA", "VLSI"]),
    FieldSpec("computer_networks", "Computer Networks", "计算机网络",
              ["computer networks", "computer network", "networking", "wireless networks", "network protocols",
               "software-defined networking", "mobile computing", "network communication", "5g", "6g"],
              ["计算机网络", "网络通信", "无线网络", "移动计算", "网络协议", "软件定义网络", "通信网络", "网络体系结构"],
              ["SDN"]),
    FieldSpec("cybersecurity", "Cybersecurity", "网络安全",
              ["cybersecurity", "cyber security", "information security", "network security", "cryptography",
               "privacy", "blockchain", "malware", "intrusion detection", "system security"],
              ["网络安全", "信息安全", "网络空间安全", "密码学", "隐私保护", "区块链", "系统安全", "安全"]),
    FieldSpec("iot", "Internet of Things", "物联网",
              ["internet of things", "wireless sensor network", "sensor networks", "cyber-physical systems",
               "edge computing", "smart city", "ubiquitous computing"],
              ["物联网", "传感器网络", "传感网", "信息物理系统", "边缘计算", "智慧城市", "泛在计算"],
              ["IoT", "IoTs", "CPS"]),
    FieldSpec("cloud_computing", "Cloud Computing", "云计算",
              ["cloud computing", "cloud", "serverless", "virtualization", "data center", "datacenter"],
              ["云计算", "云平台", "虚拟化", "数据中心"]),
    FieldSpec("distributed_systems", "Distributed Systems", "分布式系统",
              ["distributed systems", "distributed system", "distributed computing", "storage systems",
               "operating systems", "parallel and distributed", "consensus protocols", "peer-to-peer"],
              ["分布式系统", "分布式计算", "存储系统", "操作系统", "并行与分布式", "分布式"]),
    FieldSpec("nlp", "Natural Language Processing", "自然语言处理",
              ["natural language processing", "computational linguistics", "machine translation",
               "text mining", "language model", "language models", "information retrieval",
               "question answering", "dialogue systems", "speech recognition"],
              ["自然语言处理", "计算语言学", "机器翻译", "文本挖掘", "语言模型", "信息检索", "问答系统", "对话系统", "语音识别"],
              ["NLP"]),
    FieldSpec("computer_vision", "Computer Vision", "计算机视觉",
              ["computer vision", "image processing", "visual recognition", "object detection",
               "image recognition", "video analysis", "3d vision", "multimedia", "computer graphics",
               "image understanding"],
              ["计算机视觉", "图像处理", "图像识别", "目标检测", "视频分析", "三维视觉", "多媒体", "计算机图形学", "图像理解"],
              ["CV"]),
    # Extra fields so common custom inputs resolve to bilingual keyword sets.
    FieldSpec("robotics", "Robotics", "机器人",
              ["robotics", "robot", "autonomous systems", "autonomous driving", "control systems"],
              ["机器人", "自动驾驶", "无人系统", "智能控制"]),
    FieldSpec("hci", "Human-Computer Interaction", "人机交互",
              ["human-computer interaction", "human computer interaction", "user interface", "visualization",
               "virtual reality", "augmented reality"],
              ["人机交互", "可视化", "虚拟现实", "增强现实"],
              ["HCI", "VR", "AR"]),
    FieldSpec("bioinformatics", "Bioinformatics", "生物信息学",
              ["bioinformatics", "computational biology"], ["生物信息", "计算生物学"]),
    FieldSpec("signal_processing", "Signal Processing", "信号处理",
              ["signal processing", "communication systems", "wireless communication"],
              ["信号处理", "通信系统", "无线通信"]),
    FieldSpec("electrical_engineering", "Electrical Engineering", "电气工程",
              ["electrical engineering", "electronic engineering", "power systems"],
              ["电气工程", "电子工程", "电子信息", "电力系统"]),
]

_BY_KEY = {f.key: f for f in TAXONOMY}
_ALIASES: dict[str, str] = {}
for _f in TAXONOMY:
    for _s in [_f.label, _f.key.replace("_", " "), *(_f.en[:1]), *(_f.acronyms), *([_f.label_zh] if _f.label_zh else [])]:
        _ALIASES[_s.lower()] = _f.key
_ALIASES.update({
    "cs": "computer_science", "ai": "artificial_intelligence", "ml": "machine_learning",
    "it": "information_technology", "se": "software_engineering", "ds": "data_science",
    "ce": "computer_engineering", "networks": "computer_networks", "networking": "computer_networks",
    "security": "cybersecurity", "cyber security": "cybersecurity", "information security": "cybersecurity",
    "internet of things (iot)": "iot", "cloud": "cloud_computing", "deep learning": "machine_learning",
    "nlp": "nlp", "cv": "computer_vision", "vision": "computer_vision", "big data": "data_science",
})

# Department-level hints (independent of the user's fields): any of these in a
# school/department name suggests a computing-related unit.
COMPUTING_DEPT_HINTS_EN = ["computer", "computing", "software", "information", "artificial intelligence",
                           "data science", "cyber", "electronic", "intelligence", "informatics", "network"]
COMPUTING_DEPT_HINTS_ZH = ["计算机", "软件", "信息", "人工智能", "网络", "数据", "智能", "电子", "通信", "网安"]


def resolve_fields(user_fields: list[str]) -> list[FieldSpec]:
    """Map user-entered field names (EN/ZH/acronyms/custom) to FieldSpecs."""
    out: list[FieldSpec] = []
    seen: set[str] = set()
    for raw in user_fields:
        for part in re.split(r"[,，;；\n]", raw):
            name = part.strip()
            if not name:
                continue
            key = _ALIASES.get(name.lower())
            if key is None:
                for f in TAXONOMY:
                    if name.lower() in [k.lower() for k in f.en] or name in f.zh:
                        key = f.key
                        break
            if key:
                spec = _BY_KEY[key]
            else:
                ck = "custom_" + re.sub(r"\W+", "_", name.lower()).strip("_")
                spec = FieldSpec(ck, name, None, [name.lower()] if not re.search(r"[一-鿿]", name) else [],
                                 [name] if re.search(r"[一-鿿]", name) else [], custom=True)
            if spec.key not in seen:
                seen.add(spec.key)
                out.append(spec)
    return out


def _en_pattern(kw: str) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z])" + re.escape(kw) + r"(?![A-Za-z])", re.IGNORECASE)


def match_fields(text: str, fields: list[FieldSpec]) -> list[dict]:
    """Return [{key,label,keywords:[...]}] for every field with literal keyword evidence."""
    if not text:
        return []
    results = []
    for f in fields:
        hits: list[str] = []
        for kw in [f.label.lower(), *f.en]:
            if kw and _en_pattern(kw).search(text) and kw not in hits:
                hits.append(kw)
        for kw in f.zh:
            if kw in text and kw not in hits:
                hits.append(kw)
        for ac in f.acronyms:
            if re.search(r"(?<![A-Za-z])" + re.escape(ac) + r"(?![A-Za-z])", text) and ac not in hits:
                hits.append(ac)
        # "安全" alone is too generic unless paired with a network/info context
        if f.key == "cybersecurity" and hits == ["安全"]:
            hits = []
        if f.key == "cloud_computing" and hits == ["cloud"]:
            hits = []
        if hits:
            results.append({"key": f.key, "label": f.label, "keywords": hits})
    return results


def canonical_field_for(term: str) -> FieldSpec | None:
    """Best canonical field for a single research-area phrase (any language)."""
    matches = match_fields(term, TAXONOMY)
    if not matches:
        return None
    best = max(matches, key=lambda m: max(len(k) for k in m["keywords"]))
    return _BY_KEY.get(best["key"])


def english_label_for(term: str) -> str | None:
    """English rendering of a Chinese research phrase if it maps exactly to a known keyword."""
    for f in TAXONOMY:
        for i, zh in enumerate(f.zh):
            if term.strip() == zh:
                return f.label if i == 0 else _ZH_EN_EXACT.get(zh, f.label)
    return _ZH_EN_EXACT.get(term.strip())


_ZH_EN_EXACT = {
    "深度学习": "Deep Learning", "神经网络": "Neural Networks", "强化学习": "Reinforcement Learning",
    "模式识别": "Pattern Recognition", "联邦学习": "Federated Learning", "数据挖掘": "Data Mining",
    "大数据": "Big Data", "数据库": "Databases", "推荐系统": "Recommender Systems",
    "机器翻译": "Machine Translation", "信息检索": "Information Retrieval", "知识图谱": "Knowledge Graphs",
    "图像处理": "Image Processing", "目标检测": "Object Detection", "多媒体": "Multimedia",
    "计算机图形学": "Computer Graphics", "边缘计算": "Edge Computing", "区块链": "Blockchain",
    "密码学": "Cryptography", "信息安全": "Information Security", "隐私保护": "Privacy Protection",
    "无线网络": "Wireless Networks", "移动计算": "Mobile Computing", "高性能计算": "High-Performance Computing",
    "并行计算": "Parallel Computing", "嵌入式系统": "Embedded Systems", "操作系统": "Operating Systems",
    "存储系统": "Storage Systems", "软件测试": "Software Testing", "程序分析": "Program Analysis",
    "形式化方法": "Formal Methods", "大模型": "Large Models", "大语言模型": "Large Language Models",
    "语音识别": "Speech Recognition", "对话系统": "Dialogue Systems", "问答系统": "Question Answering",
    "智能系统": "Intelligent Systems", "计算机体系结构": "Computer Architecture", "虚拟化": "Virtualization",
    "数据中心": "Data Centers", "计算机科学与技术": "Computer Science and Technology",
    "计算机技术": "Computer Technology", "网络空间安全": "Cyberspace Security", "电子信息": "Electronic Information",
    "数据科学与大数据技术": "Data Science and Big Data Technology", "信息与通信工程": "Information and Communication Engineering",
    "控制科学与工程": "Control Science and Engineering", "智能科学与技术": "Intelligent Science and Technology", "人机交互": "Human-Computer Interaction", "机器人": "Robotics",
}
