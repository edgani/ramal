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
        return "Push / Build", "lagi cukup oke untuk mendorong, membangun, dan menambah langkah"
    if recovery >= 15 and pressure > -5 and avg_score >= 5:
        return "Reset / Refill", "lebih cocok untuk pulih, isi ulang tenaga, dan rapikan fondasi"
    if instability <= -20 or pressure <= -20 or avg_score <= -15:
        return "Protect / Slow Down", "lebih baik kurangi tempo, jaga energi, dan hindari dorong berlebihan"
    return "Mixed / Selective", "bagus kalau pilih langkah yang benar-benar jelas, jangan semua dipaksa sekaligus"


def alignment_bucket(consensus: ConsensusResult) -> str:
    agreement_values = [sig.agreement for sig in consensus.signals.values()]
    avg_agreement = sum(agreement_values) / len(agreement_values)
    if avg_agreement >= 75:
        return "kompak"
    if avg_agreement >= 55:
        return "lumayan kompak"
    return "masih campur"


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
            f"Untuk horizon {horizon_display(horizon)}, kondisi umum terlihat {tone}. "
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

def metric_color_html(value: float) -> str:
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
    st.markdown(
        f"""
        <div style="padding:14px 14px 10px 14px; border:1px solid rgba(255,255,255,0.08); border-radius:16px; background:rgba(255,255,255,0.03); margin-bottom:10px;">
            <div style="font-size:15px; font-weight:700; margin-bottom:6px;">{title}</div>
            <div style="font-size:13px; opacity:0.95; margin-bottom:6px;">Status: <b>{status}</b></div>
            <div style="font-size:12px; opacity:0.8; margin-bottom:8px;">Confidence: {confidence} • Agreement: {agreement}</div>
            <div style="font-size:13px; opacity:0.95;">{hint}</div>
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
        row = {"Domain": domain_display(domain)}
        for horizon in HORIZON_ORDER:
            sig = results[horizon]["consensus"].signals[domain]
            row[horizon_display(horizon)] = f"{sig.value:+.0f}"
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
    st.title("🔮 Fortune Consensus Engine")
    st.caption(
        "Framework multi-horizon yang menggabungkan beberapa sistem secara terstruktur, "
        "dengan bahasa depan yang dibuat sesimpel mungkin untuk pembaca awam."
    )

    st.info(
        "Catatan jujur: versi ini adalah **prototype framework yang repeatable**, bukan kalkulator tradisional penuh untuk BaZi/Saju, Vedic, Western natal, atau I Ching. "
        "Tujuannya: bikin fondasi app yang rapi, gampang dibaca, dan gampang di-upgrade nanti."
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
        beginner_mode = st.checkbox("Mode awam / simple", value=True)
        show_advanced = st.checkbox("Tampilkan detail advanced", value=False)
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
    with st.expander("Cara baca hasil ini biar nggak bingung", expanded=False):
        st.markdown(
            """
- **Daily** = ritme hari ini. Cocok buat lihat perlu gas, tahan, atau observasi.
- **Weekly** = tema dekat 5–7 hari.
- **Monthly** = jendela eksekusi utama. Ini biasanya lebih penting daripada daily.
- **Quarterly** = fase 3 bulan. Bagus untuk keputusan yang agak besar.
- **Yearly** = tema besar tahun. Ini konteks paling luas.

Biar nggak ketipu noise:
- jangan jadikan **daily** sebagai raja
- lihat apakah **monthly + quarterly** searah atau tabrakan
- kalau sinyalnya campur, langkah terbaik biasanya bukan gas penuh, tapi pilih yang paling jelas dulu
            """
        )


def render_overview(results: Dict[Horizon, Dict[str, object]]) -> None:
    st.subheader("Ringkasan cepat")
    cols = st.columns(5)
    for idx, horizon in enumerate(HORIZON_ORDER):
        ex = results[horizon]["explanation"]
        avg_score = average_domain_score(results[horizon]["consensus"])
        cols[idx].markdown(
            f"""
            <div style="padding:14px; border-radius:16px; border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.03); min-height:158px;">
                <div style="font-size:13px; opacity:0.8; margin-bottom:8px;">{horizon_display(horizon)}</div>
                <div style="font-size:20px; font-weight:700; margin-bottom:8px;">{label_for_value(avg_score)}</div>
                <div style="font-size:12px; opacity:0.8; margin-bottom:8px;">Posture: <b>{ex['posture']}</b></div>
                <div style="font-size:12px; opacity:0.88; line-height:1.4;">{ex['action']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_you_are_here(results: Dict[Horizon, Dict[str, object]]) -> None:
    card = build_you_are_here(results)
    c1, c2, c3 = st.columns([1.25, 1.05, 1.05])
    with c1:
        render_phase_card(
            f"You are here: {card['posture']}",
            f"Horizon yang paling dominan sekarang: {card['horizon']}. {card['detail']}",
            "Fase utama sekarang",
        )
    with c2:
        render_phase_card(
            "Area paling enak didorong",
            f"{card['best_area']}.",
            f"Alignment: {card['alignment']}",
        )
    with c3:
        render_phase_card(
            "Area paling perlu dijaga",
            f"{card['risk_area']}.",
            "Fokus perlindungan",
        )

    st.success(card["action"])


def render_cross_horizon_story(results: Dict[Horizon, Dict[str, object]]) -> None:
    st.subheader("Story lintas horizon")
    story = build_cross_horizon_story(results)
    cols = st.columns(5)
    for idx, (title, text) in enumerate(story):
        cols[idx].markdown(
            f"""
            <div style="padding:12px; border-radius:14px; border:1px solid rgba(255,255,255,0.06); background:rgba(255,255,255,0.025); min-height:138px;">
                <div style="font-weight:700; margin-bottom:8px;">{title}</div>
                <div style="font-size:13px; opacity:0.9; line-height:1.45;">{text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_horizon_tab(bundle: Dict[str, object], beginner_mode: bool, show_advanced: bool) -> None:
    explanation = bundle["explanation"]
    consensus: ConsensusResult = bundle["consensus"]
    systems: List[SystemResult] = bundle["systems"]

    st.markdown(f"### {horizon_display(consensus.horizon)}")
    st.write(explanation["summary"])

    c_top1, c_top2, c_top3 = st.columns(3)
    c_top1.metric("Posture", explanation["posture"])
    c_top2.metric("Alignment", explanation["alignment"])
    c_top3.metric("Rata-rata skor", f"{average_domain_score(consensus):+.0f}")

    st.markdown("#### Saran praktis")
    st.success(explanation["action"])

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Apa yang lagi kuat")
        for item in explanation["strengths"]:
            render_strength_box(item["domain"], item["status"], item["confidence"], item["agreement"], item["plain_hint"])

    with c2:
        st.markdown("#### Apa yang perlu hati-hati")
        for item in explanation["cautions"]:
            render_strength_box(item["domain"], item["status"], item["confidence"], item["agreement"], item["plain_hint"])

    st.markdown("#### Semua domain")
    domain_cols = st.columns(2)
    for idx, domain in enumerate(DOMAINS):
        sig = consensus.signals[domain]
        target_col = domain_cols[idx % 2]
        hint = sign_text(domain, sig.value)
        body = f"Status: {label_for_value(sig.value)} • Confidence: {confidence_label(sig.confidence)} • Agreement: {sig.agreement:.0f}%"
        target_col.markdown(
            f"""
            <div style="padding:12px 14px; border-radius:14px; border:1px solid rgba(255,255,255,0.06); background:rgba(255,255,255,0.025); margin-bottom:8px;">
                <div style="font-weight:700; margin-bottom:6px;">{domain_display(domain)}</div>
                <div style="margin-bottom:8px;"><span style="{metric_color_html(sig.value)}">{sig.value:+.0f}</span></div>
                <div style="font-size:12px; opacity:0.85; margin-bottom:6px;">{body}</div>
                <div style="font-size:12px; opacity:0.92;">{hint}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if beginner_mode:
        best_domain, best_sig = consensus.top_strengths[0]
        weak_domain, weak_sig = consensus.top_cautions[0]
        st.info(
            f"Versi singkat: di {horizon_display(consensus.horizon)} ini, yang paling enak didorong adalah **{domain_display(best_domain)}** ({label_for_value(best_sig.value)}), "
            f"sementara yang paling perlu dijaga adalah **{domain_display(weak_domain)}** ({label_for_value(weak_sig.value)})."
        )

    if show_advanced:
        with st.expander("Advanced detail: consensus & methodology", expanded=False):
            st.markdown("**Methodology notes per engine**")
            for system in systems:
                st.markdown(f"- **{system.system_name}**: {system.methodology_note}")

            st.markdown("**Raw consensus detail**")
            for domain in DOMAINS:
                sig = consensus.signals[domain]
                st.markdown(
                    f"- **{domain_display(domain)}** → value `{sig.value:+.2f}` | confidence `{sig.confidence:.2f}` | agreement `{sig.agreement:.2f}%` | conflict penalty `{sig.conflict_penalty:.2f}`"
                )

            st.markdown("**System summaries**")
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
    st.subheader("Matrix lintas horizon")
    st.caption("Biar pembaca awam langsung lihat mana yang cuma gangguan harian dan mana yang memang fase besar.")
    matrix_rows = build_matrix(results)
    st.dataframe(matrix_rows, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("One-line action map")
    band = build_summary_band(results)
    band_cols = st.columns(5)
    for idx, horizon in enumerate(HORIZON_ORDER):
        band_cols[idx].markdown(
            f"""
            <div style="padding:12px; border-radius:14px; border:1px solid rgba(255,255,255,0.06); background:rgba(255,255,255,0.025); min-height:128px;">
                <div style="font-weight:700; margin-bottom:6px;">{horizon_display(horizon)}</div>
                <div style="font-size:13px; opacity:0.9; line-height:1.45;">{band[horizon_display(horizon)]}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.subheader("Detail per horizon")
    tabs = st.tabs([horizon_display(h) for h in HORIZON_ORDER])
    for tab, horizon in zip(tabs, HORIZON_ORDER):
        with tab:
            render_horizon_tab(results[horizon], beginner_mode, show_advanced)

    st.markdown("---")
    st.subheader("Export hasil")
    export_payload = results_to_exportable(results)
    st.download_button(
        "Download hasil JSON",
        data=json.dumps(export_payload, indent=2, ensure_ascii=False),
        file_name="fortune_consensus_result.json",
        mime="application/json",
        use_container_width=False,
    )

    st.markdown("---")
    st.subheader("Apa langkah berikutnya supaya ini naik level")
    st.markdown(
        """
1. **Ganti prototype engine dengan kalkulator tradisional yang benar** untuk BaZi/Saju, Vedic, Western natal, dan I Ching.
2. **Tambahkan logging hit/miss** supaya model bisa diaudit dari waktu ke waktu.
3. **Tambahkan bahasa awam yang lebih personal** per domain dan per horizon.
4. **Pisahkan mode Basic vs Advanced** supaya pembaca awam tidak tenggelam dalam jargon.
        """
    )


if __name__ == "__main__":
    main()
