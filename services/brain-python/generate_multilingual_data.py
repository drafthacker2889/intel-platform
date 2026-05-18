"""
Multilingual synthetic threat intelligence dataset generator.

Creates 30,000+ labeled samples in English, Russian, Chinese, German.
"""

import json
import random
from pathlib import Path
from typing import List, Tuple


class MultilingualDataGenerator:
    """Generate multilingual threat intelligence training data."""
    
    # Translations of key threat terms
    CRITICAL_TEMPLATES = {
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
    
    HIGH_TEMPLATES = {
        "en": [
            "{phrase} - {actor} exploits {tech} vulnerability to gain access",
            "New {phrase} discovered: {tech} vulnerability CVE-2024-XXXXX",
            "{actor} publishes {phrase} for {tech}",
            "Active {phrase} targeting {tech} detected",
        ],
        "ru": [
            "{phrase} - {actor} эксплуатирует уязвимость {tech} для получения доступа",
            "Обнаружена новая {phrase}: уязвимость {tech} CVE-2024-XXXXX",
            "{actor} публикует {phrase} для {tech}",
            "Активная {phrase}, нацеленная на {tech}, обнаружена",
        ],
        "zh": [
            "{phrase} - {actor}利用{tech}漏洞获得访问权限",
            "发现新的{phrase}：{tech}漏洞CVE-2024-XXXXX",
            "{actor}发布{tech}的{phrase}",
            "检测到针对{tech}的活跃{phrase}",
        ],
        "de": [
            "{phrase} - {actor} nutzt {tech}-Anfälligkeit aus, um Zugriff zu erlangen",
            "Neue {phrase} entdeckt: {tech}-Sicherheitslücke CVE-2024-XXXXX",
            "{actor} veröffentlicht {phrase} für {tech}",
            "Aktiver {phrase} auf {tech} gerichtet",
        ],
    }
    
    ACTORS = {
        "en": ["LockBit", "Royal", "BlackCat", "Alphv", "Lazarus Group", "APT28"],
        "ru": ["LockBit", "Royal", "Альфа", "Лазарус", "APT28", "Fancy Bear"],
        "zh": ["LockBit", "Royal", "黑猫", "拉扎罗斯", "APT28"],
        "de": ["LockBit", "Royal", "BlackCat", "Lazarus", "APT28", "Fancy Bear"],
    }
    
    ORGS = {
        "en": ["Fortune 500 company", "healthcare provider", "financial institution"],
        "ru": ["компания Fortune 500", "поставщик здравоохранения", "финансовое учреждение"],
        "zh": ["财富500公司", "医疗保健提供者", "金融机构"],
        "de": ["Fortune-500-Unternehmen", "Gesundheitsdienstleister", "Finanzinstitution"],
    }
    
    TECHS = {
        "en": ["Windows Server", "Active Directory", "Cisco ASA", "Exchange Server"],
        "ru": ["Windows Server", "Active Directory", "Cisco ASA", "Exchange Server"],
        "zh": ["Windows服务器", "活动目录", "思科ASA", "Exchange服务器"],
        "de": ["Windows Server", "Active Directory", "Cisco ASA", "Exchange Server"],
    }
    
    PHRASES = {
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
    
    def generate(self, samples_per_language: int = 5000) -> List[dict]:
        """Generate multilingual dataset."""
        samples = []
        languages = ["en", "ru", "zh", "de"]
        
        for lang in languages:
            print(f"Generating {samples_per_language} samples in {lang.upper()}...")
            
            # Distribution per language
            critical_count = int(samples_per_language * 0.10)
            high_count = int(samples_per_language * 0.30)
            medium_count = int(samples_per_language * 0.40)
            low_count = int(samples_per_language * 0.20)
            
            for _ in range(critical_count):
                samples.append(self._generate_critical_sample(lang))
            
            for _ in range(high_count):
                samples.append(self._generate_high_sample(lang))
            
            for _ in range(medium_count):
                samples.append(self._generate_medium_sample(lang))
            
            for _ in range(low_count):
                samples.append(self._generate_low_sample(lang))
        
        random.shuffle(samples)
        return samples
    
    def _generate_critical_sample(self, lang: str) -> dict:
        """Generate a CRITICAL risk sample in specified language."""
        template = random.choice(self.CRITICAL_TEMPLATES[lang])
        actor = random.choice(self.ACTORS[lang])
        org = random.choice(self.ORGS[lang])
        phrase = random.choice(self.PHRASES[lang]["CRITICAL"])
        count = random.randint(50, 500)
        
        text = template.format(actor=actor, org=org, phrase=phrase, count=count)
        entities = [
            {"text": actor, "type": "ORG"},
            {"text": org, "type": "ORG"},
        ]
        
        return {
            "text": text,
            "expected_label": "CRITICAL",
            "language": lang,
            "entities": entities,
        }
    
    def _generate_high_sample(self, lang: str) -> dict:
        """Generate a HIGH risk sample."""
        template = random.choice(self.HIGH_TEMPLATES[lang])
        actor = random.choice(self.ACTORS[lang])
        phrase = random.choice(self.PHRASES[lang]["HIGH"])
        tech = random.choice(self.TECHS[lang])
        
        text = template.format(actor=actor, phrase=phrase, tech=tech)
        entities = [
            {"text": actor, "type": "ORG"},
            {"text": tech, "type": "PRODUCT"},
        ]
        
        return {
            "text": text,
            "expected_label": "HIGH",
            "language": lang,
            "entities": entities,
        }
    
    def _generate_medium_sample(self, lang: str) -> dict:
        """Generate a MEDIUM risk sample."""
        phrase = random.choice(self.PHRASES[lang]["MEDIUM"])
        org = random.choice(self.ORGS[lang])
        
        templates = {
            "en": f"{org} {phrase} reveals security gaps",
            "ru": f"{org} {phrase} выявляет пробелы в безопасности",
            "zh": f"{org}{phrase}揭示安全漏洞",
            "de": f"{org} {phrase} offenbaren Sicherheitslücken",
        }
        
        text = templates[lang]
        entities = [{"text": org, "type": "ORG"}]
        
        return {
            "text": text,
            "expected_label": "MEDIUM",
            "language": lang,
            "entities": entities,
        }
    
    def _generate_low_sample(self, lang: str) -> dict:
        """Generate a LOW risk sample."""
        phrase = random.choice(self.PHRASES[lang]["LOW"])
        
        templates = {
            "en": f"Latest {phrase} trends in cybersecurity",
            "ru": f"Последние тренды {phrase} в кибербезопасности",
            "zh": f"网络安全的最新{phrase}趋势",
            "de": f"Neueste {phrase}-Trends in der Cybersicherheit",
        }
        
        text = templates[lang]
        
        return {
            "text": text,
            "expected_label": "LOW",
            "language": lang,
            "entities": [],
        }


def main():
    gen = MultilingualDataGenerator()
    samples = gen.generate(samples_per_language=7500)  # 30K total
    
    output_path = Path(__file__).parent.parent / "evals" / "multilingual_eval_cases.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False)
    
    print(f"\nGenerated {len(samples)} multilingual samples to {output_path}")
    
    # Statistics
    by_lang = {}
    by_label = {}
    
    for sample in samples:
        lang = sample["language"]
        label = sample["expected_label"]
        
        by_lang[lang] = by_lang.get(lang, 0) + 1
        by_label[label] = by_label.get(label, 0) + 1
    
    print("\nLanguage distribution:")
    for lang, count in sorted(by_lang.items()):
        pct = 100 * count / len(samples)
        print(f"  {lang.upper()}: {count} ({pct:.1f}%)")
    
    print("\nLabel distribution:")
    for label, count in sorted(by_label.items()):
        pct = 100 * count / len(samples)
        print(f"  {label}: {count} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
