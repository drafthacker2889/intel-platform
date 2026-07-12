"""Language vocabularies and sentence templates.

Grouped as plain data so callers can extend or replace any piece via
``ThreatDataGenerator(vocab=...)`` without touching generation logic.
"""

from typing import Dict, List

LANGUAGES = ("en", "ru", "zh", "de")
LABELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

CRITICAL_TEMPLATES: Dict[str, List[str]] = {
    "en": [
        "{actor} leaked database dump of {org}: {phrase} for {count} employees",
        "LEAKED: {phrase} - {org} admin credentials exposed",
        "{org} breach: {phrase} found in ransomware dump by {actor}",
        "CRITICAL: {phrase} - {org} internal system compromised",
    ],
    "ru": [
        "{actor} слил базу данных {org}: {phrase} для {count} сотрудников",
        "УТЕЧКА: {phrase} - учетные данные администратора {org} разоблачены",
        "Взлом {org}: {phrase} найдены в дампе вымогателей {actor}",
        "КРИТИЧЕСКИ: {phrase} - внутренняя система {org} скомпрометирована",
    ],
    "zh": [
        "{actor}泄露了{org}的数据库转储：{phrase}涉及{count}名员工",
        "泄露：{phrase} - {org}管理员凭证已公开",
        "{org}违规事件：{phrase}发现于{actor}勒索软件转储中",
        "严重：{phrase} - {org}内部系统已被攻陷",
    ],
    "de": [
        "{actor} leckte Datenbank von {org}: {phrase} für {count} Mitarbeiter",
        "DURCHGESICKERT: {phrase} - Admin-Anmeldedaten von {org} offengelegt",
        "{org} Verstoß: {phrase} in Ransomware-Dump von {actor} gefunden",
        "KRITISCH: {phrase} - Interne Systeme von {org} kompromittiert",
    ],
}

HIGH_TEMPLATES: Dict[str, List[str]] = {
    "en": [
        "{phrase} - {actor} exploits {tech} vulnerability to gain access",
        "New {phrase} discovered: {tech} vulnerability",
        "{actor} publishes {phrase} for {tech}",
        "Active {phrase} targeting {tech} detected",
    ],
    "ru": [
        "{phrase} - {actor} эксплуатирует уязвимость {tech} для получения доступа",
        "Обнаружена новая {phrase}: уязвимость {tech}",
        "{actor} публикует {phrase} для {tech}",
        "Активная {phrase}, нацеленная на {tech}, обнаружена",
    ],
    "zh": [
        "{phrase} - {actor}利用{tech}漏洞获得访问权限",
        "发现新的{phrase}：{tech}漏洞",
        "{actor}发布{tech}的{phrase}",
        "检测到针对{tech}的活跃{phrase}",
    ],
    "de": [
        "{phrase} - {actor} nutzt {tech}-Anfälligkeit aus, um Zugriff zu erlangen",
        "Neue {phrase} entdeckt: {tech}-Sicherheitslücke",
        "{actor} veröffentlicht {phrase} für {tech}",
        "Aktiver {phrase} auf {tech} gerichtet",
    ],
}

# MEDIUM / LOW use single f-string patterns keyed by language.
MEDIUM_PATTERNS: Dict[str, str] = {
    "en": "{org} {phrase} reveals security gaps",
    "ru": "{org} {phrase} выявляет пробелы в безопасности",
    "zh": "{org}{phrase}揭示安全漏洞",
    "de": "{org} {phrase} offenbaren Sicherheitslücken",
}

LOW_PATTERNS: Dict[str, str] = {
    "en": "Latest {phrase} trends in cybersecurity",
    "ru": "Последние тренды {phrase} в кибербезопасности",
    "zh": "网络安全的最新{phrase}趋势",
    "de": "Neueste {phrase}-Trends in der Cybersicherheit",
}

ACTORS: Dict[str, List[str]] = {
    "en": ["LockBit", "Royal", "BlackCat", "Alphv", "Lazarus Group", "APT28"],
    "ru": ["LockBit", "Royal", "Альфа", "Лазарус", "APT28", "Fancy Bear"],
    "zh": ["LockBit", "Royal", "黑猫", "拉扎罗斯", "APT28"],
    "de": ["LockBit", "Royal", "BlackCat", "Lazarus", "APT28", "Fancy Bear"],
}

ORGS: Dict[str, List[str]] = {
    "en": ["Fortune 500 company", "healthcare provider", "financial institution"],
    "ru": ["компания Fortune 500", "поставщик здравоохранения", "финансовое учреждение"],
    "zh": ["财富500公司", "医疗保健提供者", "金融机构"],
    "de": ["Fortune-500-Unternehmen", "Gesundheitsdienstleister", "Finanzinstitution"],
}

TECHS: Dict[str, List[str]] = {
    "en": ["Windows Server", "Active Directory", "Cisco ASA", "Exchange Server"],
    "ru": ["Windows Server", "Active Directory", "Cisco ASA", "Exchange Server"],
    "zh": ["Windows服务器", "活动目录", "思科ASA", "Exchange服务器"],
    "de": ["Windows Server", "Active Directory", "Cisco ASA", "Exchange Server"],
}

PHRASES: Dict[str, Dict[str, List[str]]] = {
    "en": {
        "CRITICAL": ["admin password is", "database dump", "credentials leaked"],
        "HIGH": ["exploitation tutorial", "zero day vulnerability", "malware analysis"],
        "MEDIUM": ["security research", "incident response", "vulnerability assessment"],
        "LOW": ["security news", "technology update", "best practices"],
    },
    "ru": {
        "CRITICAL": ["пароль администратора", "дамп базы данных", "утечка учетных данных"],
        "HIGH": ["руководство по эксплуатации", "уязвимость нулевого дня", "анализ вредоноса"],
        "MEDIUM": ["исследование безопасности", "реагирование на инциденты", "оценка уязвимостей"],
        "LOW": ["новости безопасности", "обновление технологии", "лучшие практики"],
    },
    "zh": {
        "CRITICAL": ["管理员密码", "数据库转储", "凭证泄露"],
        "HIGH": ["利用教程", "零日漏洞", "恶意软件分析"],
        "MEDIUM": ["安全研究", "事件响应", "漏洞评估"],
        "LOW": ["安全新闻", "技术更新", "最佳实践"],
    },
    "de": {
        "CRITICAL": ["Admin-Passwort", "Datenbank-Dump", "Leaks von Anmeldedaten"],
        "HIGH": ["Exploits-Anleitung", "Zero-Day-Sicherheitslücke", "Malware-Analyse"],
        "MEDIUM": ["Sicherheitsforschung", "Incident Response", "Anfälligkeitsbewertung"],
        "LOW": ["Sicherheitsnachrichten", "Technologie-Update", "Best Practices"],
    },
}

# Default label mix (fractions must sum to 1.0).
DEFAULT_DISTRIBUTION = {"CRITICAL": 0.10, "HIGH": 0.30, "MEDIUM": 0.40, "LOW": 0.20}
