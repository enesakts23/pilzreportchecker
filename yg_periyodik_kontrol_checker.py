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
    from langdetect import detect
    LANGUAGE_DETECTION_AVAILABLE = True
except ImportError:
    LANGUAGE_DETECTION_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class YGPeriyodikKontrolCriteria:
    """YG Tesisleri Periyodik Kontrol kriterleri veri sınıfı"""
    tesis_ve_genel_bilgiler: Dict[str, Any]
    trafo_merkezi_kontrolu: Dict[str, Any]
    elektrik_guvenlik_kontrolu: Dict[str, Any]
    topraklama_sistemleri: Dict[str, Any]
    yangın_guvenlik_sistemleri: Dict[str, Any]
    is_guvenligi_malzemeleri: Dict[str, Any]

@dataclass
class YGKontrolAnalysisResult:
    """YG Kontrol analiz sonucu veri sınıfı"""
    criteria_name: str
    found: bool
    content: str
    score: int
    max_score: int
    details: Dict[str, Any]

class YGPeriyodikKontrolAnalyzer:
    """YG Tesisleri Periyodik Kontrol Formu analiz sınıfı"""
    
    def __init__(self):
        logger.info("YG Periyodik Kontrol analysis system starting...")
        
        self.criteria_weights = {
            "Tesis ve Genel Bilgiler": 15,
            "Trafo Merkezi Kontrolü": 30,
            "Elektrik Güvenlik Kontrolü": 25,
            "Topraklama Sistemleri": 15,
            "Yangın Güvenlik Sistemleri": 10,
            "İş Güvenliği Malzemeleri": 5
        }
        
        self.criteria_details = {
            "Tesis ve Genel Bilgiler": {
                "tesis_adi": {"pattern": r"(?:TESİSİN ADI|tesisinin adı|tesis adı|firma adı|şirket)", "weight": 3},
                "tarih_bilgisi": {"pattern": r"(?:tarih|dönem|kontrol tarihi|\d{1,2}[./]\d{1,2}[./]\d{4})", "weight": 3},
                "trafo_bilgileri": {"pattern": r"(?:trafo|kVA|transformer|güç|gerilim|kV)", "weight": 3},
                "firma_bilgileri": {"pattern": r"(?:ltd|şti|a\.?ş|san|tic|ltd\.şti|limited|şirket)", "weight": 3},
                "adres_bilgileri": {"pattern": r"(?:cad|cadde|sok|sokak|mahalle|mah|no:|adres)", "weight": 3}
            },
            "Trafo Merkezi Kontrolü": {
                "bransman_hat_durumu": {"pattern": r"(?:branşman hattı|hat durumu|kesit|kablo durumu)", "weight": 5},
                "enh_direkleri": {"pattern": r"(?:ENH direkleri|direk|izalatör|havai hat)", "weight": 4},
                "kapi_kontrolleri": {"pattern": r"(?:kapıların.*kilitlenebilir|kapı.*kilit|dışa.*açıl)", "weight": 4},
                "metal_topraklama": {"pattern": r"(?:metal.*topraklama|bütün metal|toprak bağlantı)", "weight": 5},
                "yg_hucreleri": {"pattern": r"(?:YG hücreleri|hücre|izole halı|panel)", "weight": 4},
                "trafo_odasi": {"pattern": r"(?:trafo odası|oda.*havalandırma|ventilasyon)", "weight": 4},
                "yanici_malzeme": {"pattern": r"(?:yanıcı malzeme|yangın.*tehlikesi|malzeme kontrolü)", "weight": 4}
            },
            "Elektrik Güvenlik Kontrolü": {
                "koruma_topraklama": {"pattern": r"(?:koruma.*topraklama|işletme topraklaması|koruma sistemi)", "weight": 5},
                "guvenlik_mesafeleri": {"pattern": r"(?:güvenlik mesafeleri|emniyet mesafe|izolasyon mesafe)", "weight": 5},
                "kablo_bara_montaj": {"pattern": r"(?:kablo.*montaj|bara.*montaj|YG kablo|elektrik bağlantı)", "weight": 4},
                "silikajel_kontrol": {"pattern": r"(?:silikajel|genleşme kap|nefes alma|trafo bakım)", "weight": 3},
                "yag_testi": {"pattern": r"(?:yağ.*test|delinme test|trafo yağı|yağ analizi)", "weight": 4},
                "havalandirma_panjur": {"pattern": r"(?:havalandırma panjur|tel kafes|ventilasyon koruması)", "weight": 3},
                "manevra_kolları": {"pattern": r"(?:manevra kol|ayırıcı.*kol|işletme kolu)", "weight": 3}
            },
            "Topraklama Sistemleri": {
                "topraklama_direnci": {"pattern": r"(?:topraklama direnci|direnç ölçüm|toprak direnci)", "weight": 6},
                "dokunma_gerilimi": {"pattern": r"(?:dokunma gerilimi|temas gerilimi|güvenlik gerilimi)", "weight": 5},
                "baglanti_kontrolu": {"pattern": r"(?:bağlantı.*gevşek|oksitlenme|bağlantı kontrol)", "weight": 4}
            },
            "Yangın Güvenlik Sistemleri": {
                "yangin_algılama": {"pattern": r"(?:yangın algılama|dedektör|duman algılama)", "weight": 4},
                "yangin_sondurme": {"pattern": r"(?:yangın söndürme|söndürme tüp|CO2|yangın sistemi)", "weight": 3},
                "acil_aydinlatma": {"pattern": r"(?:acil aydınlatma|acil çıkış|emergency)", "weight": 3}
            },
            "İş Güvenliği Malzemeleri": {
                "yg_eldiveni": {"pattern": r"(?:YG eldiveni|eldiven|izole eldiven|elektrik eldiveni)", "weight": 1},
                "izole_hali": {"pattern": r"(?:izole halı|İzole Halı|halı|elektrik halısı|yalıtkan halı)", "weight": 1},
                "tehlike_levhası": {"pattern": r"(?:tehlike levhası|Tehlike Levhaları|levha|uyarı levhası|ölüm tehlikesi)", "weight": 1},
                "izole_sehpa": {"pattern": r"(?:izole sehpa|İzole Sehpa|sehpa|yalıtkan sehpa)", "weight": 1},
                "ilk_yardim": {"pattern": r"(?:ilk yardım|İlk Yardım|talimat|işletme talimatı|İşletme Talimatı)", "weight": 1}
            }
        }
        
        # Onay durumu pattern'leri - OCR sonuçlarına göre güncellenmiş
        self.approval_patterns = {
            "uygun": r"(?:uygun|UYGUN|✓|√|✔|☑|v|V|c|C|onaylandı|kabul|geçer|ok)",
            "uygun_degil": r"(?:uygun değil|UYGUN DEĞİL|degil|DEGIL|✗|✘|×|❌|x|X|red|yetersiz|eksik)",
            "not_var": r"(?:not|açıklama|dipnot|özel durum|NOT)"
        }
    
    def detect_language(self, text: str) -> str:
        """Metin dilini tespit et"""
        if not LANGUAGE_DETECTION_AVAILABLE:
            return 'tr'
        
        try:
            sample_text = text[:500].strip()
            if not sample_text:
                return 'tr'
                
            detected_lang = detect(sample_text)
            logger.info(f"Detected language: {detected_lang}")
            return detected_lang if detected_lang in ['tr', 'en'] else 'tr'
            
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return 'tr'
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """PDF'den metin çıkar - PyPDF2 ve OCR ile"""
        pypdf_text = ""
        ocr_text = ""
        
        # Önce PyPDF2 ile dene
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        pypdf_text += page_text + "\n"
                
                if len(pypdf_text.strip()) > 50:
                    logger.info("Text extracted using PyPDF2")
                    return pypdf_text.strip()
                
        except Exception as e:
            logger.error(f"PDF text extraction error: {e}")
        
        # PyPDF2 yeterli değilse OCR kullan
        try:
            logger.info("Insufficient text with PyPDF2, trying OCR...")
            images = convert_from_path(pdf_path, dpi=300)
            
            for i, image in enumerate(images):
                try:
                    text = pytesseract.image_to_string(image, lang='tur+eng')
                    text = re.sub(r'\s+', ' ', text)
                    ocr_text += text + "\n"
                    
                    logger.info(f"OCR extracted {len(text)} characters from page {i+1}")
                    
                except Exception as page_error:
                    logger.error(f"Page {i+1} OCR error: {page_error}")
                    continue
            
            logger.info(f"OCR total text length: {len(ocr_text)}")
            return ocr_text.strip() if ocr_text.strip() else pypdf_text.strip()
            
        except Exception as e:
            logger.error(f"OCR text extraction error: {e}")
            return pypdf_text.strip()
    
    def extract_approval_status(self, text: str, criteria_text: str) -> Dict[str, Any]:
        """Onay durumunu tespit et"""
        status = {
            "uygun": False,
            "uygun_degil": False,
            "not_var": False,
            "confidence": 0.0
        }
        
        # Kriter etrafındaki metin parçasını bul
        criteria_lower = criteria_text.lower()
        text_lower = text.lower()
        
        # Kriter bulunursa etrafındaki 200 karakter al
        for keyword in criteria_lower.split():
            if keyword in text_lower:
                pos = text_lower.find(keyword)
                if pos != -1:
                    start = max(0, pos - 100)
                    end = min(len(text), pos + 200)
                    context = text[start:end]
                    
                    # Onay pattern'lerini kontrol et
                    for pattern_name, pattern in self.approval_patterns.items():
                        if re.search(pattern, context, re.IGNORECASE):
                            status[pattern_name] = True
                            status["confidence"] = 0.8
                            break
                    break
        
        return status
    
    def analyze_criteria(self, text: str, category: str) -> Dict[str, YGKontrolAnalysisResult]:
        """Kriterleri analiz et"""
        results = {}
        criteria = self.criteria_details.get(category, {})
        
        for criterion_name, criterion_data in criteria.items():
            pattern = criterion_data["pattern"]
            weight = criterion_data["weight"]
            
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            
            if matches:
                content = f"Found: {str(matches[:3])}"
                found = True
                
                # Onay durumunu kontrol et
                approval_status = self.extract_approval_status(text, str(matches[0]) if matches else "")
                
                # Skoru hesapla - daha esnek sistem
                if approval_status["uygun_degil"]:
                    score = 0  # Açıkça uygun değil
                elif approval_status["uygun"]:
                    score = weight  # Açıkça uygun
                else:
                    # Belirsiz ama kriter mevcut - optimistik yaklaşım
                    score = int(weight * 0.8)  # %80 puan ver
                    
            else:
                content = "Not found"
                found = False
                score = 0
                approval_status = {"uygun": False, "uygun_degil": False, "not_var": False, "confidence": 0.0}
            
            results[criterion_name] = YGKontrolAnalysisResult(
                criteria_name=criterion_name,
                found=found,
                content=content,
                score=score,
                max_score=weight,
                details={
                    "pattern_used": pattern,
                    "matches_count": len(matches) if matches else 0,
                    "approval_status": approval_status
                }
            )
        
        return results

    def calculate_scores(self, analysis_results: Dict[str, Dict[str, YGKontrolAnalysisResult]]) -> Dict[str, Any]:
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
        """YG Kontrol formundan özel değerleri çıkar"""
        values = {
            "tesis_adi": "Bulunamadı",
            "kontrol_tarihi": "Bulunamadı",
            "trafo_gucu": "Bulunamadı",
            "trafo_markasi": "Bulunamadı",
            "firma_adi": "Bulunamadı",
            "adres": "Bulunamadı",
            "kontrol_firmasi": "Bulunamadı",
            "genel_degerlendirme": "Bulunamadı"
        }
        
        # Tesis adı
        tesis_patterns = [
            r"TESİSİN ADI\s*([A-Za-zÇĞıİÖŞÜçğıöşü\s\.&]+)",
            r"([A-Za-zÇĞıİÖŞÜçğıöşü\s\.&]+(?:TİC|SAN|A\.Ş|LTD))"
        ]
        for pattern in tesis_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                values["tesis_adi"] = match.group(1).strip()
                break
        
        # Kontrol tarihi
        date_patterns = [
            r"Tarih:\s*(\d{1,2}[./]\d{1,2}[./]\d{4})",
            r"(\d{1,2}[./]\d{1,2}[./]\d{4})"
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                values["kontrol_tarihi"] = match.group(1).strip()
                break
        
        # Trafo gücü
        if re.search(r"(\d+)\s*kVA", text, re.IGNORECASE):
            match = re.search(r"(\d+)\s*kVA", text, re.IGNORECASE)
            values["trafo_gucu"] = f"{match.group(1)} kVA"
        
        # Trafo markası
        marka_patterns = [
            r"Trafonun markası\s*([A-Za-z]+)",
            r"markası\s*([A-Za-z]+)"
        ]
        for pattern in marka_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                values["trafo_markasi"] = match.group(1).strip()
                break
        
        # Kontrol firması
        if "NETA NORM" in text:
            values["kontrol_firmasi"] = "NETA NORM ELEKTRİK LTD.ŞTİ"
        
        # Genel değerlendirme
        degerlendirme_patterns = [
            r"GENEL DEĞERLENDİRME\s*:?\s*([A-Za-zÇĞıİÖŞÜçğıöşü\s]+)",
            r"DEĞERLENDİRME\s*([A-Za-zÇĞıİÖŞÜçğıöşü\s]+)"
        ]
        for pattern in degerlendirme_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                values["genel_degerlendirme"] = match.group(1).strip()
                break
        
        return values

    def generate_recommendations(self, analysis_results: Dict, scores: Dict) -> List[str]:
        """YG Kontrol için öneriler oluştur"""
        recommendations = []
        
        total_percentage = scores["percentage"]
        
        if total_percentage >= 70:
            recommendations.append(f"✅ YG Periyodik Kontrol GEÇERLİ (Toplam: %{total_percentage:.0f})")
        elif total_percentage >= 50:
            recommendations.append(f"🟡 YG Periyodik Kontrol KOŞULLU (Toplam: %{total_percentage:.0f})")
        else:
            recommendations.append(f"❌ YG Periyodik Kontrol YETERSİZ (Toplam: %{total_percentage:.0f})")
        
        for category, results in analysis_results.items():
            category_score = scores["category_scores"][category]["percentage"]
            
            if category_score < 50:
                recommendations.append(f"🔴 {category} bölümü yetersiz (%{category_score:.0f})")
            elif category_score < 70:
                recommendations.append(f"🟡 {category} bölümü geliştirilmeli (%{category_score:.0f})")
            else:
                recommendations.append(f"🟢 {category} bölümü yeterli (%{category_score:.0f})")
        
        if total_percentage < 70:
            recommendations.extend([
                "",
                "💡 İYİLEŞTİRME ÖNERİLERİ:",
                "- Yetersiz bulunan kontrol maddelerini tamamlayın",
                "- Güvenlik sistemlerini yeniden kontrol edin",
                "- Topraklama ölçümlerini yaptırın",
                "- İş güvenliği malzemelerini tamamlayın"
            ])
        
        return recommendations

    def analyze_yg_kontrol(self, pdf_path: str) -> Dict[str, Any]:
        """Ana YG Kontrol analiz fonksiyonu"""
        logger.info("YG Periyodik Kontrol analysis starting...")
        
        if not os.path.exists(pdf_path):
            return {"error": f"PDF dosyası bulunamadı: {pdf_path}"}
        
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            return {"error": "PDF'den metin çıkarılamadı"}
        
        detected_lang = self.detect_language(text)
        
        analysis_results = {}
        for category in self.criteria_weights.keys():
            analysis_results[category] = self.analyze_criteria(text, category)
        
        scores = self.calculate_scores(analysis_results)
        extracted_values = self.extract_specific_values(text)
        recommendations = self.generate_recommendations(analysis_results, scores)
        
        final_status = "PASS" if scores["percentage"] >= 70 else ("CONDITIONAL" if scores["percentage"] >= 50 else "FAIL")
        final_score = scores["total_score"]
        final_percentage = scores["percentage"]
        
        report = {
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_info": {
                "pdf_path": pdf_path,
                "detected_language": detected_lang
            },
            "extracted_values": extracted_values,
            "category_analyses": analysis_results,
            "scoring": scores,
            "recommendations": recommendations,
            "summary": {
                "total_score": final_score,
                "percentage": final_percentage,
                "status": final_status,
                "report_type": "YG_PERIYODIK_KONTROL"
            }
        }
        
        return report

def main():
    """Ana fonksiyon"""
    analyzer = YGPeriyodikKontrolAnalyzer()

    pdf_path = "periyodikkontrolformu.pdf"

    if not os.path.exists(pdf_path):
        print(f"❌ PDF dosyası bulunamadı: {pdf_path}")
        return
    
    print("🔍 YG Tesisleri Periyodik Kontrol Analizi Başlatılıyor...")
    print("=" * 60)
    
    report = analyzer.analyze_yg_kontrol(pdf_path)
    
    if "error" in report:
        print(f"❌ Hata: {report['error']}")
        return
    
    print("\n📊 ANALİZ SONUÇLARI")
    print("=" * 60)
    
    print(f"📅 Analiz Tarihi: {report['analysis_date']}")
    print(f"🔍 Tespit Edilen Dil: {report['file_info']['detected_language'].upper()}")
    
    print(f"📋 Toplam Puan: {report['summary']['total_score']}/100")
    print(f"📈 Yüzde: %{report['summary']['percentage']:.0f}")
    print(f"🎯 Durum: {report['summary']['status']}")
    print(f"📄 Rapor Türü: {report['summary']['report_type']}")
    
    print("\n📋 ÖNEMLİ ÇIKARILAN DEĞERLER")
    print("-" * 40)
    extracted_values = report['extracted_values']
    display_names = {
        "tesis_adi": "Tesis Adı",
        "kontrol_tarihi": "Kontrol Tarihi",
        "trafo_gucu": "Trafo Gücü",
        "trafo_markasi": "Trafo Markası",
        "firma_adi": "Firma Adı",
        "adres": "Adres",
        "kontrol_firmasi": "Kontrol Firması",
        "genel_degerlendirme": "Genel Değerlendirme"
    }
    
    for key, value in extracted_values.items():
        display_name = display_names.get(key, key.replace('_', ' ').title())
        print(f"{display_name}: {value}")
    
    print("\n📊 KATEGORİ PUANLARI")
    print("-" * 40)
    for category, score_data in report['scoring']['category_scores'].items():
        print(f"{category}: {score_data['normalized']}/{score_data['max_weight']} (%{score_data['percentage']:.0f})")
    
    print("\n💡 ÖNERİLER VE DEĞERLENDİRME")
    print("-" * 40)
    for recommendation in report['recommendations']:
        print(recommendation)
    
    print("\n📋 GENEL DEĞERLENDİRME")
    print("=" * 60)
    
    if report['summary']['percentage'] >= 70:
        print("✅ SONUÇ: GEÇERLİ")
        print(f"🌟 Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: YG Periyodik Kontrol formu gerekli kriterleri sağlamaktadır.")
        
    elif report['summary']['percentage'] >= 50:
        print("🟡 SONUÇ: KOŞULLU")
        print(f"⚠️ Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: YG Kontrol formu kabul edilebilir ancak bazı eksiklikler var.")
        
    else:
        print("❌ SONUÇ: YETERSİZ")
        print(f"⚠️ Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: YG Kontrol formu minimum gereksinimleri karşılamıyor.")

if __name__ == "__main__":
    main()
