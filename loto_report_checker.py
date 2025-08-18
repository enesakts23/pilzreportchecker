import re
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
import PyPDF2
from docx import Document
import pandas as pd
from dataclasses import dataclass, asdict
import logging
import pytesseract
from PIL import Image
from pdf2image import convert_from_path

try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
    OFFLINE_TRANSLATION_AVAILABLE = True
except ImportError:
    OFFLINE_TRANSLATION_AVAILABLE = False
    print("⚠️ Offline çeviri desteği için: pip install transformers torch sentencepiece")

try:
    from langdetect import detect
    LANGUAGE_DETECTION_AVAILABLE = True
except ImportError:
    LANGUAGE_DETECTION_AVAILABLE = False
    print("⚠️ Dil tespiti için: pip install langdetect")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class LOTOCriteria:
    """LOTO rapor kriterleri veri sınıfı"""
    genel_rapor_bilgileri: Dict[str, Any]
    tesis_makine_tanimi: Dict[str, Any]
    loto_politikasi_degerlendirmesi: Dict[str, Any]
    enerji_kaynaklari_analizi: Dict[str, Any]
    izolasyon_noktalari_prosedurler: Dict[str, Any]
    teknik_degerlendirme_sonuclar: Dict[str, Any]
    dokumantasyon_referanslar: Dict[str, Any]

@dataclass
class LOTOAnalysisResult:
    """LOTO analiz sonucu veri sınıfı"""
    criteria_name: str
    found: bool
    content: str
    score: int
    max_score: int
    details: Dict[str, Any]

class LOTOReportAnalyzer:
    """LOTO rapor analiz sınıfı"""
    
    def __init__(self):
        # Çeviri özelliğini devre dışı bırak (çoğu LOTO raporu Türkçe)
        self.translation_models = {}
        self.language_detector = None
        
        # Sadece dil tespiti kullan, çeviri yapma
        logger.info("LOTO analiz sistemi başlatılıyor (Türkçe optimized)...")
        
        self.criteria_weights = {
            "Genel Rapor Bilgileri": 15,
            "Tesis ve Makine Tanımı": 10,
            "LOTO Politikası Değerlendirmesi": 15,
            "Enerji Kaynakları Analizi": 20,
            "İzolasyon Noktaları ve Prosedürler": 20,
            "Teknik Değerlendirme ve Sonuçlar": 15,
            "Dokümantasyon ve Referanslar": 5
        }
        
        self.criteria_details = {
            "Genel Rapor Bilgileri": {
                "proje_adi_belge_no": {"pattern": r"(?:Proje\s*Ad[ıi]|Belge\s*(?:No|Numaras[ıi])|LOTO|Lockout|Tagout)", "weight": 3},
                "rapor_tarihi": {"pattern": r"(?:Rapor\s*Tarihi|Tarih)\s*[:=]\s*(\d{1,2}[./]\d{1,2}[./]\d{4})", "weight": 3},
                "versiyon_bilgisi": {"pattern": r"(?:Versiyon|Version|Rev\.?|v)\s*[:=]?\s*(\d+|[A-Z])", "weight": 2},
                "revizyon_listesi": {"pattern": r"(?:Revizyon|Revision|Değişiklik)\s*(?:Listesi|List|History)", "weight": 2},
                "hazirlayan_firma": {"pattern": r"(?:Hazırlayan|Prepared\s*by|Company|Firma)\s*[:=]\s*([^\n\r]+)", "weight": 3},
                "imza_onay": {"pattern": r"(?:İmza|Signature|Onay|Approval|İnceleyen|Reviewed)", "weight": 2}
            },
            "Tesis ve Makine Tanımı": {
                "tesis_bilgileri": {"pattern": r"(?:Tesis|Facility|Plant|Factory)\s*(?:Ad[ıi]|Name)", "weight": 2},
                "makine_tanimi": {"pattern": r"(?:Makine|Machine|Equipment)\s*(?:Tan[ıi]m[ıi]|Description)", "weight": 2},
                "makine_teknik_bilgi": {"pattern": r"(?:Üretici|Manufacturer|Seri\s*No|Serial|Model)", "weight": 2},
                "makine_fotograflari": {"pattern": r"(?:Fotoğraf|Photo|Image|Görsel|Picture)", "weight": 2},
                "lokasyon_bilgisi": {"pattern": r"(?:Lokasyon|Location|Konum|Position)", "weight": 2}
            },
            "LOTO Politikası Değerlendirmesi": {
                "mevcut_politika": {"pattern": r"(?:Politika|Policy|LOTO\s*Policy|Prosedür)", "weight": 4},
                "uygunluk_kontrol": {"pattern": r"(?:Kontrol\s*Listesi|Checklist|Evet|Hayır|Yes|No)", "weight": 3},
                "prosedur_degerlendirme": {"pattern": r"(?:Prosedür|Procedure|Değerlendirme|Assessment)", "weight": 3},
                "personel_gorusme": {"pattern": r"(?:Personel|Personnel|Görüşme|Interview|Çalışan)", "weight": 3},
                "egitim_durumu": {"pattern": r"(?:Eğitim|Training|Education|Kurs|Course)", "weight": 2}
            },
            "Enerji Kaynakları Analizi": {
                "enerji_kaynagi_tanimlama": {"pattern": r"(?:Enerji\s*Kaynağ[ıi]|Energy\s*Source|Elektrik|Electric|Pn[öo]matik|Pneumatic|Hidrolik|Hydraulic)", "weight": 5},
                "izolasyon_cihazi": {"pattern": r"(?:İzolasyon|Isolation|Disconnection|Switch|Valve|Vana)", "weight": 4},
                "cihaz_durumu": {"pattern": r"(?:Durum|Status|Çalış[ıt][ıa]r|Working|Kilitlen|Lock)", "weight": 4},
                "kilitleme_ekipmanlari": {"pattern": r"(?:Kilit|Lock|Etiket|Tag|Valf\s*Kit|Valve\s*Lock)", "weight": 4},
                "uygunsuz_enerji": {"pattern": r"(?:Uygunsuz|Unsuitable|Risk|Tehlike|Hazard)", "weight": 3}
            },
            "İzolasyon Noktaları ve Prosedürler": {
                "izolasyon_noktalari": {"pattern": r"(?:İzolasyon\s*Nokta|Isolation\s*Point|Kesme\s*Nokta)", "weight": 5},
                "prosedur_detaylari": {"pattern": r"(?:Prosedür\s*Detay|Procedure\s*Detail|Ad[ıi]m|Step)", "weight": 4},
                "mevcut_prosedur": {"pattern": r"(?:Mevcut\s*Prosedür|Current\s*Procedure|Existing)", "weight": 4},
                "tavsiyeler": {"pattern": r"(?:Tavsiye|Recommendation|Öneri|Suggestion|İyileştirme)", "weight": 4},
                "cihaz_fotograflari": {"pattern": r"(?:Cihaz.*Fotoğraf|Equipment.*Photo|Görsel.*Dokümantasyon)", "weight": 3}
            },
            "Teknik Değerlendirme ve Sonuçlar": {
                "kabul_edilebilirlik": {"pattern": r"(?:Kabul\s*Edilebilir|Acceptable|Uygun|Suitable|EVET|YES|HAYIR|NO)", "weight": 4},
                "bulgular_yorumlar": {"pattern": r"(?:Bulgu|Finding|Yorum|Comment|Tespit|Detection)", "weight": 3},
                "sonuc_tablolari": {"pattern": r"(?:Sonuç\s*Tablo|Result\s*Table|Özet|Summary)", "weight": 3},
                "oneriler": {"pattern": r"(?:Öneri|Recommendation|İyileştirme|Improvement)", "weight": 3},
                "mevzuat_uygunluk": {"pattern": r"(?:2006/42|2009/104|Direktif|Directive|EC|EN\s*ISO)", "weight": 2}
            },
            "Dokümantasyon ve Referanslar": {
                "terminoloji": {"pattern": r"(?:Terminoloji|Terminology|Tan[ıi]m|Definition)", "weight": 1},
                "kisaltmalar": {"pattern": r"(?:K[ıi]saltma|Abbreviation|Acronym)", "weight": 1},
                "mevzuat_referans": {"pattern": r"(?:Mevzuat|Legislation|Direktif|Directive|2006/42|2009/104)", "weight": 1},
                "normatif_referans": {"pattern": r"(?:EN\s*ISO\s*12100|EN\s*ISO\s*60204|EN\s*ISO\s*4414|EN\s*ISO\s*14118)", "weight": 1},
                "metodoloji": {"pattern": r"(?:Metodoloji|Methodology|Yöntem|Method|Yaklaş[ıi]m)", "weight": 1}
            }
        }
    
    def init_translation_models(self):
        """Offline çeviri modellerini başlat"""
        try:
            logger.info("Offline çeviri modelleri yükleniyor...")
            
            # Facebook NLLB modeli - daha küçük ve hızlı
            model_name = "facebook/nllb-200-distilled-600M"
            
            try:
                logger.info("NLLB çeviri modeli kontrol ediliyor...")
                tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir="./models")
                model = AutoModelForSeq2SeqLM.from_pretrained(model_name, cache_dir="./models")
                
                # NLLB için pipeline oluştur
                translator = pipeline('translation', 
                                    model=model, 
                                    tokenizer=tokenizer,
                                    device=-1)
                
                self.translation_models['nllb'] = {
                    'tokenizer': tokenizer,
                    'model': model,
                    'pipeline': translator
                }
                logger.info("✅ NLLB çeviri modeli hazır (200+ dil destekli)")
                
            except Exception as e:
                logger.warning(f"⚠️ NLLB modeli yüklenemedi: {str(e)[:100]}...")
                logger.info("Alternatif olarak Google Translate API'si kullanılabilir")
                
            if len(self.translation_models) > 0:
                logger.info(f"Çeviri sistemi aktif")
            else:
                logger.info("Çeviri modelleri yüklenemedi, sadece Türkçe desteklenecek")
                
        except Exception as e:
            logger.error(f"Çeviri modelleri başlatılamadı: {e}")
            logger.info("Çeviri özelliği devre dışı, sadece Türkçe desteklenecek")
    
    def detect_language(self, text: str) -> str:
        """Metin dilini tespit et"""
        if not LANGUAGE_DETECTION_AVAILABLE:
            return 'tr'
        
        try:
            sample_text = text[:500].strip()
            if not sample_text:
                return 'tr'
                
            detected_lang = detect(sample_text)
            logger.info(f"Tespit edilen dil: {detected_lang}")
            return detected_lang
            
        except Exception as e:
            logger.warning(f"Dil tespiti başarısız: {e}")
            return 'tr'
    
    def translate_to_turkish(self, text: str, source_lang: str) -> str:
        """Metni Türkçe'ye çevir - şimdilik devre dışı"""
        if source_lang != 'tr':
            logger.info(f"Tespit edilen dil: {source_lang.upper()} - Çeviri yapılmıyor, orijinal metin kullanılıyor")
        return text
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """PDF'den metin çıkarma - PyPDF2 ve OCR ile"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    page_text = re.sub(r'\s+', ' ', page_text)
                    page_text = page_text.replace('|', ' ')
                    text += page_text + "\n"
                
                text = text.replace('—', '-')
                text = text.replace('"', '"').replace('"', '"')
                text = text.replace('´', "'")
                text = re.sub(r'[^\x00-\x7F\u00C0-\u00FF\u0100-\u017F\u0180-\u024F]+', ' ', text)
                text = text.strip()
                
                if len(text) > 50:
                    logger.info("Metin PyPDF2 ile çıkarıldı")
                    return text
                
                logger.info("PyPDF2 ile yeterli metin bulunamadı, OCR deneniyor...")
                return self.extract_text_with_ocr(pdf_path)
                
        except Exception as e:
            logger.error(f"PDF metin çıkarma hatası: {e}")
            logger.info("OCR'a geçiliyor...")
            return self.extract_text_with_ocr(pdf_path)

    def extract_text_with_ocr(self, pdf_path: str) -> str:
        """OCR ile metin çıkarma"""
        try:
            images = convert_from_path(pdf_path, dpi=300)
            
            all_text = ""
            for i, image in enumerate(images):
                try:
                    text = pytesseract.image_to_string(image, lang='tur+eng')
                    text = re.sub(r'\s+', ' ', text)
                    text = text.replace('|', ' ')
                    all_text += text + "\n"
                    
                    logger.info(f"OCR ile sayfa {i+1}'den {len(text)} karakter çıkarıldı")
                    
                except Exception as page_error:
                    logger.error(f"Sayfa {i+1} OCR hatası: {page_error}")
                    continue
            
            all_text = all_text.replace('—', '-')
            all_text = all_text.replace('"', '"').replace('"', '"')
            all_text = all_text.replace('´', "'")
            all_text = re.sub(r'[^\x00-\x7F\u00C0-\u00FF\u0100-\u017F\u0180-\u024F]+', ' ', all_text)
            all_text = all_text.strip()
            
            logger.info(f"OCR toplam metin uzunluğu: {len(all_text)}")
            return all_text
            
        except Exception as e:
            logger.error(f"OCR metin çıkarma hatası: {e}")
            return ""
    
    def analyze_criteria(self, text: str, category: str) -> Dict[str, LOTOAnalysisResult]:
        """Kriterleri analiz et"""
        results = {}
        criteria = self.criteria_details.get(category, {})
        
        for criterion_name, criterion_data in criteria.items():
            pattern = criterion_data["pattern"]
            weight = criterion_data["weight"]
            
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            
            if matches:
                content = f"Bulunan: {str(matches[:3])}"
                found = True
                score = min(weight, len(matches) * (weight // 2))
                score = max(score, weight // 2)
            else:
                content = "Bulunamadı"
                found = False
                score = 0
            
            results[criterion_name] = LOTOAnalysisResult(
                criteria_name=criterion_name,
                found=found,
                content=content,
                score=score,
                max_score=weight,
                details={
                    "pattern_used": pattern,
                    "matches_count": len(matches) if matches else 0
                }
            )
        
        return results

    def check_date_validity(self, text: str) -> Dict[str, Any]:
        """Rapor tarih geçerliliğini kontrol et"""
        date_patterns = [
            r"(?:Rapor\s*Tarihi)\s*[:=]?\s*(\d{1,2})[./](\d{1,2})[./](\d{4})",
            r"(?:Report\s*Date)\s*[:=]?\s*(\d{1,2})[./](\d{1,2})[./](\d{4})",
            r"(?:Tarih)\s*[:=]?\s*(\d{1,2})[./](\d{1,2})[./](\d{4})",
            r"(\d{1,2})[./](\d{1,2})[./](\d{4})",
            r"(\d{4})[./](\d{1,2})[./](\d{1,2})"
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    if len(str(match[2])) == 4:  # DD/MM/YYYY format
                        day, month, year = int(match[0]), int(match[1]), int(match[2])
                    else:  # YYYY/MM/DD format
                        year, month, day = int(match[0]), int(match[1]), int(match[2])
                    
                    if 1 <= day <= 31 and 1 <= month <= 12 and 2020 <= year <= 2030:
                        report_date = datetime(year, month, day)
                        current_date = datetime.now()
                        date_diff = current_date - report_date
                        
                        is_valid = date_diff.days <= 365
                        
                        return {
                            "found": True,
                            "report_date": report_date.strftime("%d.%m.%Y"),
                            "days_old": date_diff.days,
                            "is_valid": is_valid,
                            "validity_reason": "1 yıldan eski değil" if is_valid else "1 yıldan eski - GEÇERSİZ"
                        }
                except:
                    continue
        
        return {
            "found": False,
            "report_date": "Bulunamadı",
            "days_old": 0,
            "is_valid": False,
            "validity_reason": "Rapor tarihi bulunamadı"
        }

    def calculate_scores(self, analysis_results: Dict[str, Dict[str, LOTOAnalysisResult]]) -> Dict[str, Any]:
        """Puanları hesapla"""
        category_scores = {}
        total_score = 0
        
        for category, results in analysis_results.items():
            category_max = self.criteria_weights[category]
            category_earned = sum(result.score for result in results.values())
            category_possible = sum(result.max_score for result in results.values())
            
            if category_possible > 0:
                percentage = (category_earned / category_possible) * 100
                normalized_score = (percentage / 100) * category_max
            else:
                percentage = 0
                normalized_score = 0
            
            category_scores[category] = {
                "earned": category_earned,
                "possible": category_possible,
                "normalized": round(normalized_score, 2),
                "max_weight": category_max,
                "percentage": round(percentage, 2)
            }
            
            total_score += normalized_score
        
        return {
            "category_scores": category_scores,
            "total_score": round(total_score, 2),
            "percentage": round(total_score, 2)
        }

    def extract_specific_values(self, text: str) -> Dict[str, Any]:
        """Spesifik değerleri çıkar"""
        values = {
            "proje_adi": "Bulunamadı",
            "rapor_tarihi": "Bulunamadı",
            "hazirlayan_firma": "Bulunamadı",
            "kabul_durumu": "Bulunamadı"
        }
        
        # Proje adı için daha geniş pattern'lar
        project_patterns = [
            r"(?:Proje\s*Ad[ıi])\s*[:=]\s*([^\n\r]+)",
            r"(?:Project\s*Name)\s*[:=]\s*([^\n\r]+)",
            r"LOTO.*?([A-Z][A-Za-z\s]+)",
            r"Lockout.*?Tagout.*?([A-Z][A-Za-z\s]+)"
        ]
        
        for pattern in project_patterns:
            project_match = re.search(pattern, text, re.IGNORECASE)
            if project_match:
                values["proje_adi"] = project_match.group(1).strip()[:50]
                break
        
        # Rapor tarihi için daha geniş pattern'lar
        date_patterns = [
            r"(?:Rapor\s*Tarihi)\s*[:=]?\s*(\d{1,2}[./]\d{1,2}[./]\d{4})",
            r"(?:Report\s*Date)\s*[:=]?\s*(\d{1,2}[./]\d{1,2}[./]\d{4})",
            r"(?:Tarih)\s*[:=]?\s*(\d{1,2}[./]\d{1,2}[./]\d{4})",
            r"(\d{1,2}[./]\d{1,2}[./]\d{4})",
            r"(\d{4}[./]\d{1,2}[./]\d{1,2})"
        ]
        
        for pattern in date_patterns:
            date_match = re.search(pattern, text, re.IGNORECASE)
            if date_match:
                values["rapor_tarihi"] = date_match.group(1)
                break
        
        # Hazırlayan firma için daha geniş pattern'lar
        company_patterns = [
            r"(?:Raporu\s*Hazırlayan)\s*[:=]?\s*([^\n\r]+)",
            r"(?:Hazırlayan)\s*[:=]?\s*([^\n\r]+)",
            r"(?:Prepared\s*by)\s*[:=]?\s*([^\n\r]+)",
            r"(?:Company)\s*[:=]?\s*([^\n\r]+)",
            r"(?:Firma)\s*[:=]?\s*([^\n\r]+)",
            r"PILZ\s+MAKİNE\s+EMNİYET\s+OTOMASYON",
            r"PILZ.*?OTOMASYON",
            r"(?:Prepared|Hazırlayan).*?(PILZ[^\n\r]*)",
            r"(PILZ\s+[A-Z\s]+OTOMASYON)"
        ]
        
        for pattern in company_patterns:
            company_match = re.search(pattern, text, re.IGNORECASE)
            if company_match:
                if len(company_match.groups()) > 0:
                    values["hazirlayan_firma"] = company_match.group(1).strip()[:50]
                else:
                    values["hazirlayan_firma"] = company_match.group().strip()[:50]
                break
        
        # Kabul durumu için pattern'lar
        acceptance_patterns = [
            r"(?:Kabul\s*Edilebilir|Acceptable)\s*[:=]?\s*(EVET|YES|HAYIR|NO)",
            r"(UYGUN|UYGUNSUZ|SUITABLE|UNSUITABLE)",
            r"(PASS|FAIL|GEÇERLİ|GEÇERSİZ)"
        ]
        
        for pattern in acceptance_patterns:
            acceptance_match = re.search(pattern, text, re.IGNORECASE)
            if acceptance_match:
                values["kabul_durumu"] = acceptance_match.group(1).upper()
                break
        
        return values

    def generate_recommendations(self, analysis_results: Dict, scores: Dict, date_validity: Dict) -> List[str]:
        """Öneriler oluştur"""
        recommendations = []
        
        if not date_validity["is_valid"]:
            recommendations.append("🚨 KRİTİK: Rapor tarihi 1 yıldan eski - Rapor GEÇERSİZ")
            recommendations.append(f"📅 Rapor tarihi: {date_validity['report_date']} ({date_validity['days_old']} gün eski)")
            return recommendations
        
        total_percentage = scores["percentage"]
        
        if total_percentage >= 70:
            recommendations.append(f"✅ LOTO Raporu GEÇERLİ (Toplam: %{total_percentage:.1f})")
        else:
            recommendations.append(f"❌ LOTO Raporu GEÇERSİZ (Toplam: %{total_percentage:.1f})")
        
        for category, results in analysis_results.items():
            category_score = scores["category_scores"][category]["percentage"]
            
            if category_score < 40:
                recommendations.append(f"🔴 {category} bölümü yetersiz (%{category_score:.1f})")
                missing_items = [name for name, result in results.items() if not result.found]
                if missing_items:
                    recommendations.append(f"   Eksik: {', '.join(missing_items[:3])}")
            elif category_score < 70:
                recommendations.append(f"🟡 {category} bölümü geliştirilmeli (%{category_score:.1f})")
            else:
                recommendations.append(f"🟢 {category} bölümü yeterli (%{category_score:.1f})")
        
        if total_percentage < 70:
            recommendations.extend([
                "",
                "💡 İYİLEŞTİRME ÖNERİLERİ:",
                "- Enerji kaynakları detaylı tanımlanmalı",
                "- İzolasyon noktaları eksiksiz belirtilmeli",
                "- LOTO prosedürü adımları detaylandırılmalı",
                "- Teknik değerlendirme ve sonuçlar güçlendirilmeli",
                "- Görsel dokümantasyon artırılmalı"
            ])
        
        return recommendations

    def analyze_loto_report(self, pdf_path: str) -> Dict[str, Any]:
        """Ana LOTO rapor analiz fonksiyonu"""
        logger.info("LOTO rapor analizi başlatılıyor...")
        
        if not os.path.exists(pdf_path):
            return {"error": f"PDF dosyası bulunamadı: {pdf_path}"}
        
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            return {"error": "PDF'den metin çıkarılamadı"}
        
        detected_lang = self.detect_language(text)
        
        if detected_lang != 'tr' and detected_lang in self.translation_models:
            logger.info(f"{detected_lang.upper()} dilinden Türkçe'ye çeviriliyor...")
            text = self.translate_to_turkish(text, detected_lang)
        
        date_validity = self.check_date_validity(text)
        
        analysis_results = {}
        for category in self.criteria_weights.keys():
            analysis_results[category] = self.analyze_criteria(text, category)
        
        scores = self.calculate_scores(analysis_results)
        extracted_values = self.extract_specific_values(text)
        recommendations = self.generate_recommendations(analysis_results, scores, date_validity)
        
        final_status = "PASS" if date_validity["is_valid"] and scores["percentage"] >= 70 else "FAIL"
        
        report = {
            "analiz_tarihi": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dosya_bilgisi": {
                "pdf_path": pdf_path,
                "detected_language": detected_lang
            },
            "tarih_gecerliligi": date_validity,
            "cikarilan_degerler": extracted_values,
            "kategori_analizleri": analysis_results,
            "puanlama": scores,
            "oneriler": recommendations,
            "ozet": {
                "toplam_puan": scores["total_score"],
                "yuzde": scores["percentage"],
                "durum": final_status,
                "rapor_tipi": "LOTO"
            }
        }
        
        return report

    def save_report_to_excel(self, report: Dict, output_path: str):
        """Raporu Excel'e kaydet"""
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            summary_data = {
                'Kriter': ['Toplam Puan', 'Yüzde', 'Durum', 'Rapor Tipi', 'Tarih Geçerliliği'],
                'Değer': [
                    report['ozet']['toplam_puan'],
                    f"%{report['ozet']['yuzde']}",
                    report['ozet']['durum'],
                    report['ozet']['rapor_tipi'],
                    "Geçerli" if report['tarih_gecerliligi']['is_valid'] else "Geçersiz"
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Özet', index=False)
            
            values_data = []
            for key, value in report['cikarilan_degerler'].items():
                values_data.append({'Kriter': key, 'Değer': str(value)})
            pd.DataFrame(values_data).to_excel(writer, sheet_name='Çıkarılan_Değerler', index=False)
            
            for category, results in report['kategori_analizleri'].items():
                category_data = []
                for criterion, result in results.items():
                    category_data.append({
                        'Kriter': criterion,
                        'Bulundu': result.found,
                        'İçerik': result.content,
                        'Puan': result.score,
                        'Maksimum Puan': result.max_score
                    })
                sheet_name = category.replace('/', '_').replace('\\', '_')[:31]
                pd.DataFrame(category_data).to_excel(writer, sheet_name=sheet_name, index=False)

        logger.info(f"Rapor Excel'e kaydedildi: {output_path}")

    def save_report_to_json(self, report: Dict, output_path: str):
        """Raporu JSON'a kaydet"""
        json_report = {}
        for key, value in report.items():
            if key == 'kategori_analizleri':
                json_report[key] = {}
                for category, results in value.items():
                    json_report[key][category] = {}
                    for criterion, result in results.items():
                        json_report[key][category][criterion] = asdict(result)
            else:
                json_report[key] = value

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_report, f, ensure_ascii=False, indent=2)

        logger.info(f"Rapor JSON'a kaydedildi: {output_path}")

def main():
    """Ana fonksiyon"""
    analyzer = LOTOReportAnalyzer()

    pdf_path = "lotoreport2.pdf"

    if not os.path.exists(pdf_path):
        print(f"❌ PDF dosyası bulunamadı: {pdf_path}")
        return
    
    print("🔒 LOTO Rapor Analizi Başlatılıyor...")
    print("=" * 60)
    
    report = analyzer.analyze_loto_report(pdf_path)
    
    if "error" in report:
        print(f"❌ Hata: {report['error']}")
        return
    
    print("\n📊 ANALİZ SONUÇLARI")
    print("=" * 60)
    
    print(f"📅 Analiz Tarihi: {report['analiz_tarihi']}")
    print(f"🔍 Tespit Edilen Dil: {report['dosya_bilgisi']['detected_language'].upper()}")
    print(f"📋 Toplam Puan: {report['ozet']['toplam_puan']}/100")
    print(f"📈 Yüzde: %{report['ozet']['yuzde']}")
    print(f"🎯 Durum: {report['ozet']['durum']}")
    print(f"📄 Rapor Tipi: {report['ozet']['rapor_tipi']}")
    
    print(f"\n📅 TARİH GEÇERLİLİĞİ")
    print("-" * 40)
    date_info = report['tarih_gecerliligi']
    print(f"Rapor Tarihi: {date_info['report_date']}")
    print(f"Yaş: {date_info['days_old']} gün")
    print(f"Geçerlilik: {date_info['validity_reason']}")
    
    print("\n📋 ÖNEMLİ ÇIKARILAN DEĞERLER")
    print("-" * 40)
    for key, value in report['cikarilan_degerler'].items():
        display_name = {
            "proje_adi": "Proje Adı",
            "rapor_tarihi": "Rapor Tarihi", 
            "hazirlayan_firma": "Hazırlayan Firma",
            "kabul_durumu": "Kabul Durumu"
        }.get(key, key.replace('_', ' ').title())
        print(f"{display_name}: {value}")
    
    print("\n📊 KATEGORİ PUANLARI")
    print("-" * 40)
    for category, score_data in report['puanlama']['category_scores'].items():
        print(f"{category}: {score_data['normalized']}/{score_data['max_weight']} (%{score_data['percentage']:.1f})")
    
    print("\n💡 ÖNERİLER VE DEĞERLENDİRME")
    print("-" * 40)
    for recommendation in report['oneriler']:
        print(recommendation)
    
    print("\n📋 GENEL DEĞERLENDİRME")
    print("=" * 60)
    
    if not report['tarih_gecerliligi']['is_valid']:
        print("❌ SONUÇ: GEÇERSİZ")
        print(f"🚨 KRİTİK: Rapor tarihi 1 yıldan eski ({report['tarih_gecerliligi']['days_old']} gün)")
        print("📝 Değerlendirme: Tarih geçerliliği nedeniyle rapor kabul edilemez.")
    elif report['ozet']['yuzde'] >= 70:
        print("✅ SONUÇ: GEÇERLİ")
        print(f"🌟 Toplam Başarı: %{report['ozet']['yuzde']:.1f}")
        print("📝 Değerlendirme: LOTO raporu genel olarak yeterli kriterleri sağlamaktadır.")
    else:
        print("❌ SONUÇ: GEÇERSİZ")
        print(f"⚠️ Toplam Başarı: %{report['ozet']['yuzde']:.1f}")
        print("📝 Değerlendirme: LOTO raporu minimum gereklilikleri sağlamamaktadır.")
        
        print("\n⚠️ EKSİK GEREKLİLİKLER:")
        for category, results in report['kategori_analizleri'].items():
            missing_items = []
            for criterion, result in results.items():
                if not result.found:
                    missing_items.append(criterion)
            
            if missing_items:
                print(f"\n🔍 {category}:")
                for item in missing_items:
                    readable_name = item.replace('_', ' ').title()
                    print(f"   ❌ {readable_name}")
        
        print("\n📌 YAPILMASI GEREKENLER:")
        print("1. Eksik belgelendirmeleri tamamlayın")
        print("2. Enerji kaynakları ve izolasyon noktalarını detaylandırın")
        print("3. LOTO prosedürlerini eksiksiz tanımlayın")
        print("4. Teknik değerlendirme ve sonuçları güçlendirin")
        print("5. Görsel dokümantasyonu artırın")
        print("6. Mevzuat referanslarını ekleyin")

if __name__ == "__main__":
    main()
