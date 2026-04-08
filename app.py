from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import hashlib
import json
import math
import statistics

import streamlit as st


# ============================================================
# 1) CONFIG
# ============================================================

st.set_page_config(
    page_title="Fortune Consensus Engine",
    page_icon="🔮",
    layout="wide",
)


class Horizon(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


DOMAINS = [
    "career",
    "money",
    "relationship",
    "health_stress",
    "decision_quality",
    "expansion",
    "recovery",
    "instability",
    "creativity",
    "inner_pressure",
]

DOMAIN_META = {
    "career": {
        "name": "Karier / kerja",
        "positive_hint": "lebih enak untuk dorong kerjaan, eksekusi, dan tanggung jawab",
        "negative_hint": "lebih baik rapikan fondasi kerja dulu, jangan terlalu dipaksa",
    },
    "money": {
        "name": "Uang / finansial",
        "positive_hint": "lebih enak untuk atur peluang finansial dengan disiplin",
        "negative_hint": "lebih baik konservatif dan jaga pengeluaran / risiko",
    },
    "relationship": {
        "name": "Relasi",
        "positive_hint": "lebih enak untuk komunikasi, koneksi, dan pendekatan yang halus",
        "negative_hint": "lebih rawan salah paham atau drama kalau terlalu impulsif",
    },
    "health_stress": {
        "name": "Kondisi fisik & stres",
        "positive_hint": "ritme badan dan pikiran relatif lebih mendukung",
        "negative_hint": "butuh jaga ritme, tidur, recovery, dan batasi beban berlebih",
    },
    "decision_quality": {
        "name": "Kualitas keputusan",
        "positive_hint": "lebih enak untuk ambil keputusan dengan kepala dingin",
        "negative_hint": "lebih rawan buru-buru atau bias, jadi cek ulang keputusan penting",
    },
    "expansion": {
        "name": "Ekspansi / dorong maju",
        "positive_hint": "lebih cocok untuk mendorong hal baru dan ambil langkah maju",
        "negative_hint": "lebih cocok menahan diri dan jangan paksa ekspansi",
    },
    "recovery": {
        "name": "Pemulihan / recharge",
        "positive_hint": "waktu yang oke untuk pulih, reset, dan isi ulang tenaga",
        "negative_hint": "pemulihan terasa kurang optimal, jadi kurangi overdrive",
    },
    "instability": {
        "name": "Ketidakstabilan / naik turun",
        "positive_hint": "fluktuasi relatif lebih rendah dan ritme lebih stabil",
        "negative_hint": "naik-turunnya lebih tinggi, jadi jangan terlalu reaktif",
    },
    "creativity": {
        "name": "Kreativitas",
        "positive_hint": "ide, improvisasi, dan sense kreatif lebih hidup",
        "negative_hint": "ide bisa macet atau terlalu scattered, jadi sederhanakan fokus",
    },
    "inner_pressure": {
        "name": "Tekanan batin / beban pikiran",
        "positive_hint": "beban batin relatif lebih ringan dan pikiran lebih lega",
        "negative_hint": "beban pikiran lebih berat, jadi jangan terlalu keras ke diri sendiri",
    },
}

HORIZON_WEIGHTS: Dict[Horizon, Dict[str, float]] = {
    Horizon.YEARLY: {"bazi": 0.40, "vedic": 0.35, "western": 0.25, "iching": 0.00},
    Horizon.QUARTERLY: {"bazi": 0.35, "vedic": 0.35, "western": 0.30, "iching": 0.00},
    Horizon.MONTHLY: {"bazi": 0.30, "vedic": 0.35, "western": 0.35, "iching": 0.00},
    Horizon.WEEKLY: {"bazi": 0.15, "vedic": 0.30, "western": 0.35, "iching": 0.20},
    Horizon.DAILY: {"bazi": 0.15, "vedic": 0.20, "western": 0.30, "iching": 0.35},
}

HORIZON_INTENSITY = {
    Horizon.DAILY: 0.85,
    Horizon.WEEKLY: 0.70,
    Horizon.MONTHLY: 0.55,
    Horizon.QUARTERLY: 0.42,
    Horizon.YEARLY: 0.32,
}

HORIZON_ORDER = [
    Horizon.DAILY,
    Horizon.WEEKLY,
    Horizon.MONTHLY,
    Horizon.QUARTERLY,
    Horizon.YEARLY,
]

PRIMARY_HORIZON_ORDER = [
    Horizon.MONTHLY,
    Horizon.QUARTERLY,
    Horizon.WEEKLY,
    Horizon.YEARLY,
    Horizon.DAILY,
]


# ============================================================
# 2) DATA MODELS
# ============================================================

@dataclass
class BirthProfile:
    name: str
    birth_date: str
    birth_time: str
    birth_place: str
    timezone: str = "Asia/Jakarta"


@dataclass
class ContextInput:
    question: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class DomainSignal:
    value: float
    confidence: float
    explanation: str

    def clamped(self) -> "DomainSignal":
        return DomainSignal(
            value=max(-100.0, min(100.0, self.value)),
            confidence=max(0.0, min(100.0, self.confidence)),
            explanation=self.explanation,
        )


@dataclass
class SystemResult:
    system_name: str
    horizon: Horizon
    signals: Dict[str, DomainSignal]
    summary: str
    methodology_note: str


@dataclass
class ConsensusSignal:
    value: float
    confidence: float
    agreement: float
    conflict_penalty: float
    explanation: str


@dataclass
class ConsensusResult:
    horizon: Horizon
    signals: Dict[str, ConsensusSignal]
    top_strengths: List[Tuple[str, ConsensusSignal]] = field(default_factory=list)
    top_cautions: List[Tuple[str, ConsensusSignal]] = field(default_factory=list)
    overall_summary: str = ""


# ============================================================
# 3) UTILS
# ============================================================

def stable_hash_int(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def stable_unit(text: str) -> float:
    return (stable_hash_int(text) % 10_000_000) / 10_000_000.0


def stable_signed(text: str, amplitude: float = 1.0) -> float:
    return (stable_unit(text) * 2.0 - 1.0) * amplitude


def profile_seed(profile: BirthProfile) -> str:
    return f"{profile.name}|{profile.birth_date}|{profile.birth_time}|{profile.birth_place}|{profile.timezone}"


def parse_birth_numbers(profile: BirthProfile) -> Dict[str, int]:
    try:
        y, m, d = [int(x) for x in profile.birth_date.split("-")]
    except Exception:
        y, m, d = 1990, 1, 1
    try:
        hh, mm = [int(x) for x in profile.birth_time.split(":")]
    except Exception:
        hh, mm = 12, 0
    return {"year": y, "month": m, "day": d, "hour": hh, "minute": mm}


def series_clamp(x: float) -> float:
    return max(-100.0, min(100.0, x))


def label_for_value(value: float) -> str:
    if value >= 60:
        return "sangat mendukung"
    if value >= 30:
        return "cukup mendukung"
    if value >= 10:
        return "sedikit mendukung"
    if value > -10:
        return "netral / campuran"
    if value > -30:
        return "agak menantang"
    if value > -60:
        return "cukup menantang"
    return "sangat menantang"


def confidence_label(conf: float) -> str:
    if conf >= 80:
        return "tinggi"
    if conf >= 60:
        return "cukup tinggi"
    if conf >= 40:
        return "sedang"
    return "rendah"


def simple_value_text(value: float) -> str:
    if value >= 35:
        return "lagi cukup bagus"
    if value >= 12:
        return "lumayan oke"
    if value > -12:
        return "campur"
    if value > -35:
        return "perlu hati-hati"
    return "lagi agak berat"


def plain_domain_sentence(domain: str, value: float) -> str:
    name = domain_display(domain).lower()
    if value >= 35:
        return f"Untuk {name}, fasenya lagi cukup bagus dan relatif enak didorong dengan rapi."
    if value >= 12:
        return f"Untuk {name}, arahnya lumayan oke, jadi bisa jalan pelan tapi tetap maju."
    if value > -12:
        return f"Untuk {name}, sinyalnya masih campur, jadi lebih baik lihat respons dulu sebelum nambah langkah."
    if value > -35:
        return f"Untuk {name}, mending lebih hati-hati dan jangan terlalu dipaksa."
    return f"Untuk {name}, fasenya lagi agak berat, jadi fokus utamanya jaga ritme dan kurangi tekanan yang tidak perlu."


def quick_read_sentence(domain: str, value: float) -> str:
    if value >= 20:
        return DOMAIN_META[domain]["positive_hint"].capitalize() + "."
    if value <= -20:
        return DOMAIN_META[domain]["negative_hint"].capitalize() + "."
    return f"Untuk {DOMAIN_META[domain]['name'].lower()}, lebih baik jalan secukupnya dulu sambil lihat arah yang lebih jelas."


def simple_alignment_text(label: str) -> str:
    mapping = {
        "searah": "cukup searah",
        "lumayan searah": "lumayan nyambung",
        "tarik-menarik": "masih tarik-menarik",
    }
    return mapping.get(label, label)


def horizon_plain_name(h: Horizon) -> str:
    return {
        Horizon.DAILY: "Hari ini",
        Horizon.WEEKLY: "7 hari ke depan",
        Horizon.MONTHLY: "1 bulan ke depan",
        Horizon.QUARTERLY: "3 bulan ke depan",
        Horizon.YEARLY: "1 tahun ke depan",
    }[h]


def horizon_role_text(h: Horizon) -> str:
    return {
        Horizon.DAILY: "cocok buat lihat ritme dan sikap hari ini",
        Horizon.WEEKLY: "cocok buat lihat arah dekat",
        Horizon.MONTHLY: "ini biasanya jendela eksekusi utama",
        Horizon.QUARTERLY: "ini nunjukin fase yang sedang berjalan",
        Horizon.YEARLY: "ini konteks besar tahun ini",
    }[h]


def horizon_display(h: Horizon) -> str:
    return {
        Horizon.DAILY: "Daily",
        Horizon.WEEKLY: "Weekly",
        Horizon.MONTHLY: "Monthly",
        Horizon.QUARTERLY: "Quarterly",
        Horizon.YEARLY: "Yearly",
    }[h]


def domain_display(domain: str) -> str:
    return DOMAIN_META[domain]["name"]


def sign_text(domain: str, value: float) -> str:
    return DOMAIN_META[domain]["positive_hint"] if value >= 0 else DOMAIN_META[domain]["negative_hint"]


def average_domain_score(consensus: ConsensusResult) -> float:
    return sum(sig.value for sig in consensus.signals.values()) / len(consensus.signals)


def posture_from_consensus(consensus: ConsensusResult) -> Tuple[str, str]:
    expansion = consensus.signals["expansion"].value
    decision = consensus.signals["decision_quality"].value
    recovery = consensus.signals["recovery"].value
    instability = consensus.signals["instability"].value
    pressure = consensus.signals["inner_pressure"].value
    avg_score = average_domain_score(consensus)

    if expansion >= 20 and decision >= 15 and instability > -15 and pressure > -15:
        return "Gas pelan tapi maju", "lagi cukup oke untuk melangkah, nambah progres, dan dorong hal yang memang penting"
    if recovery >= 15 and pressure > -5 and avg_score >= 5:
        return "Isi ulang dulu", "lebih cocok buat pulih, atur napas, dan rapikan dasar sebelum lanjut"
    if instability <= -20 or pressure <= -20 or avg_score <= -15:
        return "Pelankan dan jaga", "lebih baik kurangi tempo, jaga energi, dan jangan paksa hal yang belum siap"
    return "Pilih yang paling jelas", "langkah terbaik adalah pilih yang paling masuk akal dulu, jangan semua dibawa maju bareng"


def alignment_bucket(consensus: ConsensusResult) -> str:
    agreement_values = [sig.agreement for sig in consensus.signals.values()]
    avg_agreement = sum(agreement_values) / len(agreement_values)
    if avg_agreement >= 75:
        return "searah"
    if avg_agreement >= 55:
        return "lumayan searah"
    return "tarik-menarik"


def concise_primary_message(consensus: ConsensusResult) -> str:
    posture, detail = posture_from_consensus(consensus)
    return f"{posture} — {detail}."


def results_to_exportable(results: Dict[Horizon, Dict[str, object]]) -> Dict[str, object]:
    export = {}
    for horizon in HORIZON_ORDER:
        bundle = results[horizon]
        consensus: ConsensusResult = bundle["consensus"]
        explanation = bundle["explanation"]
        systems: List[SystemResult] = bundle["systems"]
        export[horizon.value] = {
            "summary": explanation["summary"],
            "action": explanation["action"],
            "strengths": explanation["strengths"],
            "cautions": explanation["cautions"],
            "systems": [
                {
                    "name": s.system_name,
                    "summary": s.summary,
                    "methodology_note": s.methodology_note,
                }
                for s in systems
            ],
            "raw_consensus": {
                domain: {
                    "value": sig.value,
                    "confidence": sig.confidence,
                    "agreement": sig.agreement,
                    "conflict_penalty": sig.conflict_penalty,
                }
                for domain, sig in consensus.signals.items()
            },
        }
    return export


# ============================================================
# 4) ENGINE BASE
# ============================================================

class BaseDivinationEngine:
    engine_name: str = "base"
    methodology_note: str = ""

    def run(
        self,
        profile: BirthProfile,
        horizon: Horizon,
        context: Optional[ContextInput] = None,
    ) -> SystemResult:
        raise NotImplementedError


# ============================================================
# 5) PROTOTYPE ENGINES
# ============================================================
# Honest note:
# These are deterministic prototype engines that imitate the idea of
# structured systems. They are NOT full traditional calculators yet.
# They exist so the app can run, explain, and be extended cleanly.
# ============================================================

class BaziEngine(BaseDivinationEngine):
    engine_name = "bazi"
    methodology_note = (
        "Prototype engine berbasis pola tetap dari profil lahir. "
        "Bukan kalkulator BaZi tradisional penuh; ini placeholder terstruktur yang repeatable."
    )

    def run(self, profile: BirthProfile, horizon: Horizon, context: Optional[ContextInput] = None) -> SystemResult:
        nums = parse_birth_numbers(profile)
        seed = profile_seed(profile)
        intensity = HORIZON_INTENSITY[horizon]

        year_mod = ((nums["year"] % 10) - 4.5) / 4.5
        month_wave = math.sin((nums["month"] / 12.0) * 2 * math.pi)
        day_wave = math.cos((nums["day"] / 31.0) * 2 * math.pi)
        time_wave = math.sin(((nums["hour"] + nums["minute"] / 60.0) / 24.0) * 2 * math.pi)

        base_map = {
            "career": 22 * year_mod + 14 * month_wave,
            "money": 18 * day_wave + 12 * year_mod,
            "relationship": 16 * time_wave - 10 * year_mod,
            "health_stress": 14 * month_wave + 8 * day_wave,
            "decision_quality": 12 * year_mod + 15 * time_wave,
            "expansion": 20 * month_wave + 10 * year_mod,
            "recovery": -12 * time_wave + 15 * day_wave,
            "instability": -15 * day_wave + 10 * month_wave,
            "creativity": 18 * time_wave + 6 * day_wave,
            "inner_pressure": -18 * time_wave - 8 * month_wave,
        }

        signals = {}
        for domain in DOMAINS:
            jitter = stable_signed(f"bazi|{seed}|{horizon.value}|{domain}", amplitude=10.0 * intensity)
            raw = (base_map[domain] * (1.0 - intensity * 0.35)) + jitter
            conf = 68 - (abs(jitter) * 0.45)
            signals[domain] = DomainSignal(
                value=series_clamp(raw),
                confidence=max(35.0, min(85.0, conf)),
                explanation=(
                    f"{domain_display(domain)} dibaca dari struktur dasar profil lahir. "
                    f"Sinyal prototipe cenderung {label_for_value(raw)}."
                ),
            )

        return SystemResult(
            system_name=self.engine_name,
            horizon=horizon,
            signals=signals,
            summary="Mesin prototipe berbasis pola dasar profil lahir yang relatif stabil.",
            methodology_note=self.methodology_note,
        )


class VedicEngine(BaseDivinationEngine):
    engine_name = "vedic"
    methodology_note = (
        "Prototype engine yang meniru ide natal + timing layer. "
        "Belum memakai kalkulasi Vedic/Jyotisha tradisional penuh."
    )

    def run(self, profile: BirthProfile, horizon: Horizon, context: Optional[ContextInput] = None) -> SystemResult:
        nums = parse_birth_numbers(profile)
        seed = profile_seed(profile)
        intensity = HORIZON_INTENSITY[horizon]

        lunar_bias = math.sin((nums["day"] / 30.0) * 2 * math.pi)
        solar_bias = math.cos((nums["month"] / 12.0) * 2 * math.pi)
        hour_bias = math.cos((nums["hour"] / 24.0) * 2 * math.pi)
        year_bias = math.sin((nums["year"] % 60) / 60.0 * 2 * math.pi)

        base_map = {
            "career": 18 * solar_bias + 10 * year_bias,
            "money": 10 * solar_bias + 16 * lunar_bias,
            "relationship": 18 * lunar_bias + 8 * hour_bias,
            "health_stress": 12 * hour_bias + 10 * solar_bias,
            "decision_quality": 14 * solar_bias - 8 * lunar_bias + 6 * hour_bias,
            "expansion": 20 * year_bias + 10 * solar_bias,
            "recovery": 14 * lunar_bias - 8 * solar_bias,
            "instability": -12 * hour_bias - 10 * lunar_bias,
            "creativity": 16 * lunar_bias + 10 * year_bias,
            "inner_pressure": -14 * hour_bias - 10 * year_bias,
        }

        signals = {}
        for domain in DOMAINS:
            jitter = stable_signed(f"vedic|{seed}|{horizon.value}|{domain}", amplitude=11.0 * intensity)
            raw = (base_map[domain] * (1.0 - intensity * 0.30)) + jitter
            conf = 70 - (abs(jitter) * 0.42)
            signals[domain] = DomainSignal(
                value=series_clamp(raw),
                confidence=max(38.0, min(86.0, conf)),
                explanation=(
                    f"{domain_display(domain)} dibaca dari kombinasi pola inti dan timing prototipe. "
                    f"Sinyalnya cenderung {label_for_value(raw)}."
                ),
            )

        return SystemResult(
            system_name=self.engine_name,
            horizon=horizon,
            signals=signals,
            summary="Mesin prototipe yang memberi bobot lebih besar pada timing menengah hingga panjang.",
            methodology_note=self.methodology_note,
        )


class WesternNatalEngine(BaseDivinationEngine):
    engine_name = "western"
    methodology_note = (
        "Prototype engine yang meniru konsep natal chart + transit light overlay. "
        "Belum memakai ephemeris / chart astrology tradisional penuh."
    )

    def run(self, profile: BirthProfile, horizon: Horizon, context: Optional[ContextInput] = None) -> SystemResult:
        nums = parse_birth_numbers(profile)
        seed = profile_seed(profile)
        intensity = HORIZON_INTENSITY[horizon]

        cardinal = ((nums["month"] - 1) % 4) - 1.5
        cardinal_bias = cardinal / 1.5
        day_bias = math.sin(nums["day"] * 0.33)
        time_bias = math.cos(nums["hour"] * 0.21)
        year_bias = math.sin((nums["year"] % 28) / 28.0 * 2 * math.pi)

        base_map = {
            "career": 15 * cardinal_bias + 12 * year_bias,
            "money": 12 * day_bias + 10 * year_bias,
            "relationship": 18 * time_bias - 6 * cardinal_bias,
            "health_stress": 12 * time_bias + 8 * day_bias,
            "decision_quality": 10 * cardinal_bias + 14 * time_bias,
            "expansion": 16 * year_bias + 10 * cardinal_bias,
            "recovery": 10 * day_bias - 10 * time_bias,
            "instability": -16 * time_bias + 10 * year_bias,
            "creativity": 14 * day_bias + 12 * cardinal_bias,
            "inner_pressure": -12 * day_bias - 12 * time_bias,
        }

        signals = {}
        for domain in DOMAINS:
            jitter = stable_signed(f"western|{seed}|{horizon.value}|{domain}", amplitude=12.0 * intensity)
            raw = (base_map[domain] * (1.0 - intensity * 0.28)) + jitter
            conf = 66 - (abs(jitter) * 0.40)
            signals[domain] = DomainSignal(
                value=series_clamp(raw),
                confidence=max(34.0, min(84.0, conf)),
                explanation=(
                    f"{domain_display(domain)} dibaca dari struktur inti plus overlay timing ringan. "
                    f"Sinyalnya terlihat {label_for_value(raw)}."
                ),
            )

        return SystemResult(
            system_name=self.engine_name,
            horizon=horizon,
            signals=signals,
            summary="Mesin prototipe yang lebih responsif untuk weekly sampai daily.",
            methodology_note=self.methodology_note,
        )


class IChingEngine(BaseDivinationEngine):
    engine_name = "iching"
    methodology_note = (
        "Prototype situational overlay berbasis pertanyaan/konteks. "
        "Belum memakai casting hexagram tradisional penuh."
    )

    def run(self, profile: BirthProfile, horizon: Horizon, context: Optional[ContextInput] = None) -> SystemResult:
        seed = profile_seed(profile)
        intensity = HORIZON_INTENSITY[horizon]
        q = (context.question or "") if context else ""
        n = (context.notes or "") if context else ""
        combined = f"{seed}|{horizon.value}|{q}|{n}"

        horizon_multiplier = {
            Horizon.DAILY: 1.00,
            Horizon.WEEKLY: 0.90,
            Horizon.MONTHLY: 0.60,
            Horizon.QUARTERLY: 0.20,
            Horizon.YEARLY: 0.10,
        }[horizon]

        question_bias = stable_signed(f"q|{combined}", amplitude=22.0 * horizon_multiplier)
        caution_bias = stable_signed(f"c|{combined}", amplitude=18.0 * horizon_multiplier)
        clarity_bias = stable_signed(f"d|{combined}", amplitude=16.0 * horizon_multiplier)

        base_map = {
            "career": question_bias * 0.6,
            "money": question_bias * 0.5,
            "relationship": -caution_bias * 0.5,
            "health_stress": -caution_bias * 0.7,
            "decision_quality": clarity_bias * 0.9,
            "expansion": question_bias * 0.7,
            "recovery": -question_bias * 0.4 - caution_bias * 0.2,
            "instability": caution_bias * -1.0,
            "creativity": clarity_bias * 0.6,
            "inner_pressure": caution_bias * -0.9,
        }

        signals = {}
        for domain in DOMAINS:
            jitter = stable_signed(f"iching|{combined}|{domain}", amplitude=8.0 * intensity * horizon_multiplier)
            raw = base_map[domain] + jitter
            conf = 58 + (10 * horizon_multiplier) - (abs(jitter) * 0.35)
            signals[domain] = DomainSignal(
                value=series_clamp(raw),
                confidence=max(25.0, min(78.0, conf)),
                explanation=(
                    f"{domain_display(domain)} dibaca dari konteks pertanyaan saat ini. "
                    f"Ini lebih cocok sebagai overlay situasi, bukan fondasi jangka panjang."
                ),
            )

        return SystemResult(
            system_name=self.engine_name,
            horizon=horizon,
            signals=signals,
            summary="Situational overlay yang paling terasa di daily dan weekly.",
            methodology_note=self.methodology_note,
        )


# ============================================================
# 6) CONSENSUS ENGINE
# ============================================================

class ConsensusEngine:
    def __init__(self, weights: Dict[Horizon, Dict[str, float]]):
        self.weights = weights

    @staticmethod
    def _weighted_mean(pairs: List[Tuple[float, float]]) -> float:
        total_weight = sum(w for _, w in pairs)
        if total_weight == 0:
            return 0.0
        return sum(v * w for v, w in pairs) / total_weight

    @staticmethod
    def _agreement_score(values: List[float]) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return 100.0
        std_dev = statistics.pstdev(values)
        return max(0.0, 100.0 - (std_dev * 1.9))

    @staticmethod
    def _conflict_penalty(values: List[float]) -> float:
        if not values:
            return 0.0
        has_pos = any(v > 10 for v in values)
        has_neg = any(v < -10 for v in values)
        if has_pos and has_neg:
            spread = max(values) - min(values)
            return min(30.0, spread * 0.14)
        return 0.0

    def combine(self, horizon: Horizon, results: List[SystemResult]) -> ConsensusResult:
        horizon_weights = self.weights[horizon]
        final_signals: Dict[str, ConsensusSignal] = {}

        for domain in DOMAINS:
            weighted_values = []
            raw_values = []
            confidence_pairs = []
            explanations = []

            for result in results:
                system_weight = horizon_weights.get(result.system_name, 0.0)
                signal = result.signals[domain].clamped()
                weighted_values.append((signal.value, system_weight))
                raw_values.append(signal.value)
                confidence_pairs.append((signal.confidence, system_weight))
                explanations.append(f"{result.system_name}: {signal.explanation}")

            mean_value = self._weighted_mean(weighted_values)
            mean_confidence = self._weighted_mean(confidence_pairs)
            agreement = self._agreement_score(raw_values)
            conflict_penalty = self._conflict_penalty(raw_values)

            final_signals[domain] = ConsensusSignal(
                value=series_clamp(mean_value),
                confidence=max(0.0, min(100.0, mean_confidence - conflict_penalty)),
                agreement=agreement,
                conflict_penalty=conflict_penalty,
                explanation=" | ".join(explanations),
            )

        sorted_by_value = sorted(final_signals.items(), key=lambda x: x[1].value, reverse=True)
        top_strengths = sorted_by_value[:3]
        top_cautions = sorted(final_signals.items(), key=lambda x: x[1].value)[:3]
        summary = self._build_overall_summary(horizon, final_signals, top_strengths, top_cautions)

        return ConsensusResult(
            horizon=horizon,
            signals=final_signals,
            top_strengths=top_strengths,
            top_cautions=top_cautions,
            overall_summary=summary,
        )

    @staticmethod
    def _build_overall_summary(
        horizon: Horizon,
        signals: Dict[str, ConsensusSignal],
        top_strengths: List[Tuple[str, ConsensusSignal]],
        top_cautions: List[Tuple[str, ConsensusSignal]],
    ) -> str:
        avg_score = sum(sig.value for sig in signals.values()) / len(signals)

        if avg_score >= 30:
            tone = "cukup mendukung"
        elif avg_score >= 10:
            tone = "lumayan mendukung"
        elif avg_score <= -30:
            tone = "cukup berat"
        elif avg_score <= -10:
            tone = "agak berat"
        else:
            tone = "campuran"

        strengths = ", ".join(domain_display(d) for d, _ in top_strengths)
        cautions = ", ".join(domain_display(d) for d, _ in top_cautions)

        return (
            f"Untuk horizon {horizon_plain_name(horizon)}, kondisi umum terlihat {tone}. "
            f"Area yang paling didukung: {strengths}. "
            f"Area yang perlu lebih hati-hati: {cautions}."
        )


# ============================================================
# 7) EXPLAINER
# ============================================================

class PlainLanguageExplainer:
    def explain_horizon(self, consensus: ConsensusResult) -> Dict[str, object]:
        strengths = []
        cautions = []

        for domain, sig in consensus.top_strengths:
            strengths.append({
                "domain": domain_display(domain),
                "status": label_for_value(sig.value),
                "confidence": confidence_label(sig.confidence),
                "agreement": f"{sig.agreement:.0f}%",
                "plain_hint": sign_text(domain, sig.value),
            })

        for domain, sig in consensus.top_cautions:
            cautions.append({
                "domain": domain_display(domain),
                "status": label_for_value(sig.value),
                "confidence": confidence_label(sig.confidence),
                "agreement": f"{sig.agreement:.0f}%",
                "plain_hint": sign_text(domain, sig.value),
            })

        posture, posture_detail = posture_from_consensus(consensus)

        return {
            "summary": consensus.overall_summary,
            "strengths": strengths,
            "cautions": cautions,
            "action": self._suggest_action(consensus),
            "posture": posture,
            "posture_detail": posture_detail,
            "alignment": alignment_bucket(consensus),
        }

    def _suggest_action(self, consensus: ConsensusResult) -> str:
        career = consensus.signals["career"].value
        money = consensus.signals["money"].value
        relationship = consensus.signals["relationship"].value
        decision = consensus.signals["decision_quality"].value
        instability = consensus.signals["instability"].value
        stress = consensus.signals["health_stress"].value
        inner_pressure = consensus.signals["inner_pressure"].value

        if decision >= 25 and career >= 15 and money >= 10 and instability >= -10:
            return "Lagi lebih cocok untuk bergerak, eksekusi, dan memanfaatkan momentum dengan tetap rapi."
        if instability <= -20 or stress <= -20 or inner_pressure <= -20:
            return "Lagi lebih cocok untuk menurunkan tempo, hindari keputusan impulsif, dan fokus rapikan ritme dulu."
        if relationship <= -15 and decision <= 5:
            return "Komunikasi lebih baik dibuat sederhana. Jangan terlalu cepat menyimpulkan atau bereaksi."
        if career >= 10 and money < 5:
            return "Bagus untuk bangun fondasi kerja dan kualitas eksekusi, tapi soal uang tetap pakai mode konservatif."
        return "Sinyalnya campuran. Gerak secukupnya, lihat respons, lalu tambah langkah kalau ritmenya mulai jelas."


# ============================================================
# 8) ORCHESTRATOR
# ============================================================

class FortuneOrchestrator:
    def __init__(self) -> None:
        self.engines: List[BaseDivinationEngine] = [
            BaziEngine(),
            VedicEngine(),
            WesternNatalEngine(),
            IChingEngine(),
        ]
        self.consensus_engine = ConsensusEngine(HORIZON_WEIGHTS)
        self.explainer = PlainLanguageExplainer()

    def run_for_horizon(
        self,
        profile: BirthProfile,
        horizon: Horizon,
        context: Optional[ContextInput] = None,
    ) -> Dict[str, object]:
        system_results = [engine.run(profile, horizon, context) for engine in self.engines]
        consensus = self.consensus_engine.combine(horizon, system_results)
        explanation = self.explainer.explain_horizon(consensus)

        return {
            "horizon": horizon,
            "systems": system_results,
            "consensus": consensus,
            "explanation": explanation,
        }

    def run_all(self, profile: BirthProfile, context: Optional[ContextInput] = None) -> Dict[Horizon, Dict[str, object]]:
        return {h: self.run_for_horizon(profile, h, context) for h in HORIZON_ORDER}


# ============================================================
# 9) UI HELPERS
# ============================================================

def badge_style_for_value(value: float) -> str:
    if value >= 30:
        bg = "rgba(34,197,94,0.18)"
        fg = "#bbf7d0"
    elif value >= 10:
        bg = "rgba(132,204,22,0.16)"
        fg = "#d9f99d"
    elif value > -10:
        bg = "rgba(148,163,184,0.16)"
        fg = "#e2e8f0"
    elif value > -30:
        bg = "rgba(250,204,21,0.16)"
        fg = "#fde68a"
    else:
        bg = "rgba(239,68,68,0.16)"
        fg = "#fecaca"
    return f"background:{bg}; color:{fg}; padding:8px 12px; border-radius:12px; display:inline-block; font-weight:600;"


def render_strength_box(title: str, status: str, confidence: str, agreement: str, hint: str) -> None:
    meta_line = ""
    if confidence or agreement:
        meta_bits = []
        if confidence:
            meta_bits.append(f"Keyakinan: {confidence}")
        if agreement:
            meta_bits.append(f"Kekompakan: {agreement}")
        meta_line = f'<div style="font-size:12px; opacity:0.75; margin-bottom:8px;">{" • ".join(meta_bits)}</div>'
    st.markdown(
        f"""
        <div style="padding:14px 14px 10px 14px; border:1px solid rgba(255,255,255,0.08); border-radius:16px; background:rgba(255,255,255,0.03); margin-bottom:10px;">
            <div style="font-size:15px; font-weight:700; margin-bottom:6px;">{title}</div>
            <div style="font-size:13px; opacity:0.88; margin-bottom:8px;">Kesannya: <b>{status}</b></div>
            {meta_line}
            <div style="font-size:13px; opacity:0.95; line-height:1.5;">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_phase_card(title: str, body: str, badge: str) -> None:
    st.markdown(
        f"""
        <div style="padding:16px; border-radius:18px; border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.03); min-height:150px;">
            <div style="font-size:12px; opacity:0.75; margin-bottom:8px;">{badge}</div>
            <div style="font-size:20px; font-weight:700; margin-bottom:10px;">{title}</div>
            <div style="font-size:14px; opacity:0.92; line-height:1.5;">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_matrix(results: Dict[Horizon, Dict[str, object]]) -> List[Dict[str, object]]:
    rows = []
    for domain in DOMAINS:
        row = {"Area hidup": domain_display(domain)}
        for horizon in HORIZON_ORDER:
            sig = results[horizon]["consensus"].signals[domain]
            row[horizon_plain_name(horizon)] = simple_value_text(sig.value)
        rows.append(row)
    return rows


def build_summary_band(results: Dict[Horizon, Dict[str, object]]) -> Dict[str, str]:
    out = {}
    for horizon in HORIZON_ORDER:
        ex = results[horizon]["explanation"]
        out[horizon_display(horizon)] = ex["action"]
    return out


def detect_primary_horizon(results: Dict[Horizon, Dict[str, object]]) -> Horizon:
    best_horizon = Horizon.MONTHLY
    best_score = -10_000.0
    for horizon in PRIMARY_HORIZON_ORDER:
        consensus: ConsensusResult = results[horizon]["consensus"]
        avg_score = average_domain_score(consensus)
        avg_conf = sum(sig.confidence for sig in consensus.signals.values()) / len(consensus.signals)
        avg_agree = sum(sig.agreement for sig in consensus.signals.values()) / len(consensus.signals)
        weighted = avg_score + (avg_conf * 0.12) + (avg_agree * 0.08)
        if weighted > best_score:
            best_score = weighted
            best_horizon = horizon
    return best_horizon


def build_you_are_here(results: Dict[Horizon, Dict[str, object]]) -> Dict[str, str]:
    primary = detect_primary_horizon(results)
    consensus: ConsensusResult = results[primary]["consensus"]
    ex = results[primary]["explanation"]
    posture, detail = posture_from_consensus(consensus)
    alignment = alignment_bucket(consensus)
    top_domain, top_sig = consensus.top_strengths[0]
    low_domain, low_sig = consensus.top_cautions[0]

    return {
        "horizon": horizon_display(primary),
        "posture": posture,
        "detail": detail,
        "alignment": alignment,
        "best_area": f"{domain_display(top_domain)} ({label_for_value(top_sig.value)})",
        "risk_area": f"{domain_display(low_domain)} ({label_for_value(low_sig.value)})",
        "action": ex["action"],
    }


def build_cross_horizon_story(results: Dict[Horizon, Dict[str, object]]) -> List[Tuple[str, str]]:
    story = []
    for horizon in [Horizon.DAILY, Horizon.WEEKLY, Horizon.MONTHLY, Horizon.QUARTERLY, Horizon.YEARLY]:
        consensus: ConsensusResult = results[horizon]["consensus"]
        posture, detail = posture_from_consensus(consensus)
        story.append((horizon_display(horizon), f"{posture} — {detail}"))
    return story


# ============================================================
# 10) STREAMLIT APP
# ============================================================

def app_header() -> None:
    st.title("🔮 Peta Fase Pribadi")
    st.caption(
        "Bacaan multi-horizon dengan penjelasan langsung: apa yang lagi enak didorong, apa yang perlu dijaga, dan langkah paling masuk akal sekarang — tanpa harus baca angka dulu."
    )

    st.info(
        "Catatan jujur: versi ini masih **prototype yang repeatable**, jadi anggap sebagai kerangka baca yang rapi dan konsisten dulu — belum kalkulator tradisional penuh."
    )


def sidebar_form() -> Tuple[BirthProfile, ContextInput, bool, bool]:
    with st.sidebar:
        st.header("Input")
        name = st.text_input("Nama", value="Edward")
        birth_date = st.text_input("Tanggal lahir (YYYY-MM-DD)", value="1988-01-01")
        birth_time = st.text_input("Jam lahir (HH:MM)", value="12:00")
        birth_place = st.text_input("Tempat lahir", value="Jakarta, Indonesia")
        timezone = st.text_input("Timezone", value="Asia/Jakarta")
        question = st.text_area(
            "Fokus / pertanyaan saat ini",
            value="Sekarang lagi lebih cocok buat dorong kerjaan baru atau tahan dulu?",
            height=90,
        )
        notes = st.text_area(
            "Catatan tambahan",
            value="Bikin output yang gampang dimengerti orang awam.",
            height=80,
        )
        beginner_mode = st.checkbox("Pakai bahasa yang lebih awam", value=True)
        show_advanced = st.checkbox("Tampilkan detail teknis (opsional)", value=False)
        st.button("Jalankan engine", use_container_width=True)

    profile = BirthProfile(
        name=name,
        birth_date=birth_date,
        birth_time=birth_time,
        birth_place=birth_place,
        timezone=timezone,
    )
    context = ContextInput(question=question, notes=notes)
    return profile, context, beginner_mode, show_advanced


def render_beginner_guide() -> None:
    with st.expander("Cara paling gampang baca hasil ini", expanded=False):
        st.markdown(
            """
**Cara baca yang paling aman:**

- Anggap ini seperti **pembacaan fase**, bukan vonis hidup.
- Baca **1 bulan ke depan** dulu. Itu biasanya bagian yang paling enak dipakai buat ambil sikap.
- Cek **3 bulan ke depan** buat tahu apakah arah 1 bulan ini cuma sesaat atau memang bagian dari fase yang lebih besar.
- Lihat **Hari ini** cuma untuk tahu kapan enak maju, kapan mending ngerem sedikit.

**Kalau semua terasa campur:**

- jangan paksa semua area hidup maju bareng
- pilih satu hal yang paling jelas responsnya
- yang belum jelas cukup dijaga ritmenya dulu
            """
        )


def horizon_narrative(consensus: ConsensusResult) -> Dict[str, str]:
    best_domain, best_sig = consensus.top_strengths[0]
    weak_domain, weak_sig = consensus.top_cautions[0]
    posture, posture_detail = posture_from_consensus(consensus)
    avg_score = average_domain_score(consensus)

    if avg_score >= 18:
        opening = f"Secara umum, {horizon_plain_name(consensus.horizon).lower()} ini kelihatannya lagi cukup kebuka."
    elif avg_score <= -18:
        opening = f"Secara umum, {horizon_plain_name(consensus.horizon).lower()} ini terasa lebih berat dan butuh ritme yang lebih rapi."
    else:
        opening = f"Secara umum, {horizon_plain_name(consensus.horizon).lower()} ini sinyalnya masih campur, jadi enaknya jangan terlalu buru-buru."

    focus = (
        f"Kalau harus pilih satu fokus, yang paling enak didorong sekarang adalah {domain_display(best_domain).lower()}. "
        f"{quick_read_sentence(best_domain, best_sig.value)}"
    )
    caution = (
        f"Yang paling perlu dijaga adalah {domain_display(weak_domain).lower()}. "
        f"{quick_read_sentence(weak_domain, weak_sig.value)}"
    )
    closing = f"Arah besarnya: {posture.lower()}, jadi sikap terbaiknya adalah {posture_detail}."
    return {
        "opening": opening,
        "focus": focus,
        "caution": caution,
        "closing": closing,
    }


def render_overview(results: Dict[Horizon, Dict[str, object]]) -> None:
    st.subheader("Kalau mau baca cepat")
    for horizon in [Horizon.MONTHLY, Horizon.QUARTERLY, Horizon.WEEKLY, Horizon.DAILY, Horizon.YEARLY]:
        consensus: ConsensusResult = results[horizon]["consensus"]
        narrative = horizon_narrative(consensus)
        st.markdown(
            f"""
            <div style="padding:16px; border-radius:16px; border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.03); margin-bottom:10px;">
                <div style="font-size:12px; opacity:0.7; margin-bottom:8px;">{horizon_plain_name(horizon)}</div>
                <div style="font-size:15px; line-height:1.65;">
                    <b>{narrative['opening']}</b> {narrative['focus']} {narrative['caution']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_you_are_here(results: Dict[Horizon, Dict[str, object]]) -> None:
    card = build_you_are_here(results)
    st.subheader("Bacaan utama sekarang")
    st.markdown(
        f"""
        <div style="padding:18px; border-radius:18px; border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.035);">
            <div style="font-size:12px; opacity:0.72; margin-bottom:8px;">Kalau cuma ambil inti, baca bagian ini</div>
            <div style="font-size:24px; font-weight:700; margin-bottom:12px;">Sekarang fasenya: {card['posture']}</div>
            <div style="font-size:15px; line-height:1.7; opacity:0.95;">
                Yang paling dominan sekarang itu bacaan <b>{card['horizon']}</b>. Artinya, fokus utamanya bukan di semua hal sekaligus, tapi di ritme fase yang sekarang lagi paling terasa. 
                Dari semua area, yang paling kebuka sekarang ada di <b>{card['best_area']}</b>. 
                Sementara itu, yang paling perlu dijaga ada di <b>{card['risk_area']}</b>. 
                Jadi sikap terbaiknya: {card['action']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_cross_horizon_story(results: Dict[Horizon, Dict[str, object]]) -> None:
    st.subheader("Cerita fasenya dari dekat ke jauh")
    order = [Horizon.DAILY, Horizon.WEEKLY, Horizon.MONTHLY, Horizon.QUARTERLY, Horizon.YEARLY]
    for horizon in order:
        consensus: ConsensusResult = results[horizon]["consensus"]
        narrative = horizon_narrative(consensus)
        st.markdown(
            f"""
            <div style="padding:14px 16px; border-radius:14px; border:1px solid rgba(255,255,255,0.06); background:rgba(255,255,255,0.025); margin-bottom:8px;">
                <div style="font-weight:700; margin-bottom:6px;">{horizon_plain_name(horizon)}</div>
                <div style="font-size:14px; opacity:0.94; line-height:1.6;">
                    {narrative['opening']} {narrative['closing']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_horizon_tab(bundle: Dict[str, object], beginner_mode: bool, show_advanced: bool) -> None:
    explanation = bundle["explanation"]
    consensus: ConsensusResult = bundle["consensus"]
    systems: List[SystemResult] = bundle["systems"]
    horizon = consensus.horizon
    narrative = horizon_narrative(consensus)

    best_domain, best_sig = consensus.top_strengths[0]
    weak_domain, weak_sig = consensus.top_cautions[0]

    st.markdown(f"### {horizon_plain_name(horizon)}")
    st.markdown(
        f"""
        <div style="padding:18px; border-radius:16px; border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.035); margin-bottom:12px;">
            <div style="font-size:16px; line-height:1.75;">
                <b>{narrative['opening']}</b><br><br>
                {narrative['focus']}<br><br>
                {narrative['caution']}<br><br>
                {narrative['closing']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Jadi kalau mau disederhanakan")
    st.success(explanation["action"])

    st.markdown("#### Yang lagi kebuka")
    for item in explanation["strengths"]:
        hint = item["plain_hint"] if beginner_mode else f"{item['plain_hint']} ({item['status']}, keyakinan {item['confidence']}, kekompakan {item['agreement']})"
        st.markdown(f"- **{item['domain']}** — {hint}")

    st.markdown("#### Yang mending jangan dipaksa")
    for item in explanation["cautions"]:
        hint = item["plain_hint"] if beginner_mode else f"{item['plain_hint']} ({item['status']}, keyakinan {item['confidence']}, kekompakan {item['agreement']})"
        st.markdown(f"- **{item['domain']}** — {hint}")

    st.markdown("#### Penjelasan per area")
    for domain in DOMAINS:
        sig = consensus.signals[domain]
        st.markdown(
            f"""
            <div style="padding:12px 14px; border-radius:14px; border:1px solid rgba(255,255,255,0.06); background:rgba(255,255,255,0.022); margin-bottom:8px;">
                <div style="font-weight:700; margin-bottom:6px;">{domain_display(domain)}</div>
                <div style="font-size:14px; line-height:1.6; opacity:0.94;">{plain_domain_sentence(domain, sig.value)}</div>
                <div style="font-size:13px; line-height:1.55; opacity:0.82; margin-top:6px;">{quick_read_sentence(domain, sig.value)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.info(
        f"Inti {horizon_plain_name(horizon).lower()}: lebih enak dorong **{domain_display(best_domain)}**, dan lebih baik jaga ritme di **{domain_display(weak_domain)}**."
    )

    if show_advanced:
        with st.expander("Detail advanced: angka dan metodologi", expanded=False):
            st.markdown("**Catatan metode per engine**")
            for system in systems:
                st.markdown(f"- **{system.system_name}**: {system.methodology_note}")

            st.markdown("**Angka detail consensus**")
            for domain in DOMAINS:
                sig = consensus.signals[domain]
                st.markdown(
                    f"- **{domain_display(domain)}** → value `{sig.value:+.2f}` | confidence `{sig.confidence:.2f}` | agreement `{sig.agreement:.2f}%` | conflict penalty `{sig.conflict_penalty:.2f}`"
                )

            st.markdown("**Ringkasan per sistem**")
            for system in systems:
                st.markdown(f"- **{system.system_name}**: {system.summary}")


# ============================================================
# 11) MAIN
# ============================================================

def main() -> None:
    app_header()
    profile, context, beginner_mode, show_advanced = sidebar_form()

    orchestrator = FortuneOrchestrator()
    results = orchestrator.run_all(profile, context)

    render_beginner_guide()
    render_you_are_here(results)
    st.markdown("---")
    render_overview(results)

    st.markdown("---")
    render_cross_horizon_story(results)

    st.markdown("---")
    st.subheader("Kalau mau lihat lebih detail")
    st.caption("Bagian bawah ini buat baca per waktu dengan gaya yang lebih runtut, bukan angka-angka.")
    tabs = st.tabs([horizon_plain_name(h) for h in HORIZON_ORDER])
    for tab, horizon in zip(tabs, HORIZON_ORDER):
        with tab:
            render_horizon_tab(results[horizon], beginner_mode, show_advanced)

    st.markdown("---")
    st.subheader("Simpan hasil")
    export_payload = results_to_exportable(results)
    st.download_button(
        "Download hasil JSON",
        data=json.dumps(export_payload, indent=2, ensure_ascii=False),
        file_name="fortune_consensus_result.json",
        mime="application/json",
        use_container_width=False,
    )

    st.markdown("---")
    st.subheader("Kalau nanti mau dinaikkan levelnya")
    st.markdown(
        """
1. **Ganti prototype engine dengan kalkulator tradisional yang benar** untuk BaZi/Saju, Vedic, Western natal, dan I Ching.
2. **Tambahkan logging hit/miss** supaya model bisa diaudit dari waktu ke waktu.
3. **Perhalus gaya bahasa** supaya hasilnya makin berasa seperti pembacaan manusia, bukan app.
4. **Pisahkan mode Basic vs Advanced** supaya pembaca awam tetap nyaman, sementara yang detail tetap tersedia.
        """
    )


if __name__ == "__main__":
    main()
