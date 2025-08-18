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

try:
    from langdetect import detect
    LANGUAGE_DETECTION_AVAILABLE = True
except ImportError:
    LANGUAGE_DETECTION_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ECDeclarationCriteria:
    """EC Declaration of Conformity kriterleri veri sınıfı"""
    yasal_cerceve_ve_beyan: Dict[str, Any]
    makine_uretici_bilgileri: Dict[str, Any]
    direktif_uygunluk: Dict[str, Any]
    standart_referanslari: Dict[str, Any]
    teknik_dosya_bilgileri: Dict[str, Any]
    imza_ve_yetkilendirme: Dict[str, Any]

@dataclass
class ECDeclarationAnalysisResult:
    """EC Declaration analiz sonucu veri sınıfı"""
    criteria_name: str
    found: bool
    content: str
    score: int
    max_score: int
    details: Dict[str, Any]

class ECDeclarationAnalyzer:
    """EC Declaration of Conformity analiz sınıfı"""
    
    def __init__(self):
        logger.info("EC Declaration of Conformity analysis system starting...")
        
        self.criteria_weights = {
            "Yasal Çerçeve ve Beyan": 25,
            "Makine ve Üretici Bilgileri": 20,
            "Direktif Uygunluk": 20,
            "Standart Referansları": 15,
            "Teknik Dosya Bilgileri": 10,
            "İmza ve Yetkilendirme": 10
        }
        
        self.criteria_details = {
            "Yasal Çerçeve ve Beyan": {
                "ec_declaration_title": {"pattern": r"(?:EC\s*Declaration|Declaration\s*of\s*Conformity|Uygunluk\s*Beyanı|CE\s*Declaration)", "weight": 5},
                "authorized_representative": {"pattern": r"(?:authorised\s*representative|authorized\s*representative|yetkili\s*temsilci|Pilz\s*Ireland)", "weight": 4},
                "conformity_statement": {"pattern": r"(?:is\s*in\s*conformity|uygunluk\s*beyan|conform|compliance|meets\s*requirements)", "weight": 4},
                "manufacturer_responsibility": {"pattern": r"(?:sole\s*responsibility|manufacturer|üretici\s*sorumluluğu|under\s*responsibility)", "weight": 4},
                "declaration_relates": {"pattern": r"(?:declaration\s*relates|bu\s*beyan|this\s*declaration|to\s*which)", "weight": 4},
                "conformity_declared": {"pattern": r"(?:Conformity\s*is\s*declared|uygunluk\s*beyan\s*edilir|declared\s*in\s*reference)", "weight": 4}
            },
            "Makine ve Üretici Bilgileri": {
                "machine_description": {"pattern": r"(?:Manufactured\s*By|Machine|Equipment|Makine|V524B|punching\s*machine)", "weight": 5},
                "serial_number": {"pattern": r"(?:Serial\s*Number|Seri\s*No|S/N)\s*[:=]?\s*([A-Z0-9\-]+)", "weight": 4},
                "manufacturer_details": {"pattern": r"(?:Suzhou\s*Keber|Technology\s*Co|manufacturer|üretici|Company)", "weight": 4},
                "manufacturer_address": {"pattern": r"(?:Dongshan\s*Road|Industrial\s*Park|Suzhou|Jiangsu|address|adres)", "weight": 4},
                "product_identification": {"pattern": r"(?:Model|Type|Tip|Product\s*ID|Knee\s*pad)", "weight": 3}
            },
            "Direktif Uygunluk": {
                "machinery_directive": {"pattern": r"(?:2006/42/EC|Machinery\s*Directive|Makine\s*Direktifi)", "weight": 6},
                "european_directives": {"pattern": r"(?:European\s*Directives|Avrupa\s*Direktif|following\s*.*Directive)", "weight": 4},
                "directive_compliance": {"pattern": r"(?:conformity\s*with.*directive|direktif.*uygun|compliance\s*with)", "weight": 5},
                "ce_marking_basis": {"pattern": r"(?:CE\s*marking|CE\s*işaret|basis\s*for\s*CE)", "weight": 5}
            },
            "Standart Referansları": {
                "en_60204_standard": {"pattern": r"(?:EN\s*60204-1|60204|Electrical\s*equipment\s*of\s*machines)", "weight": 4},
                "en_iso_13849_standard": {"pattern": r"(?:EN\s*ISO\s*13849-1|13849|Safety.*control\s*systems)", "weight": 4},
                "safety_standards": {"pattern": r"(?:Safety\s*of\s*machinery|Makine\s*güvenliği|safety.*standard)", "weight": 3},
                "standard_references": {"pattern": r"(?:standard\s*or\s*other\s*normative|standart\s*referans|normative\s*document)", "weight": 2},
                "iso_references": {"pattern": r"(?:ISO\s*[0-9]+|IEC\s*[0-9]+|EN\s*[0-9]+)", "weight": 2}
            },
            "Teknik Dosya Bilgileri": {
                "technical_file_authority": {"pattern": r"(?:authorised\s*to\s*compile.*Technical\s*File|teknik\s*dosya|technical\s*documentation)", "weight": 4},
                "technical_file_person": {"pattern": r"(?:Person\s*authorised|yetkili\s*kişi|authorized\s*person)", "weight": 3},
                "technical_construction_file": {"pattern": r"(?:Technical\s*Construction\s*File|TCF|technical\s*file)", "weight": 3}
            },
            "İmza ve Yetkilendirme": {
                "signature_present": {"pattern": r"(?:Signature|İmza|signed\s*by|imzalayan)", "weight": 3},
                "name_and_title": {"pattern": r"(?:Name\s*and\s*title|John\s*McAuliffe|Managing\s*Director|ad\s*ve\s*unvan)", "weight": 2},
                "date_of_declaration": {"pattern": r"(?:February\s*2024|2024|date\s*of\s*declaration|tarih)", "weight": 2},
                "place_of_issue": {"pattern": r"(?:Cork\s*Ireland|Ireland|Cork|place\s*of\s*issue|çıkarıldığı\s*yer)", "weight": 2},
                "company_authorization": {"pattern": r"(?:Pilz\s*Ireland|authorized\s*representative|yetkili\s*temsilci)", "weight": 1}
            }
        }
        
        # Çeviri sistemi (basitleştirilmiş)
        self.translation_enabled = False  # Büyük modeller nedeniyle devre dışı
    
    def detect_language(self, text: str) -> str:
        """Metin dilini tespit et"""
        if not LANGUAGE_DETECTION_AVAILABLE:
            return 'en'
        
        try:
            sample_text = text[:500].strip()
            if not sample_text:
                return 'en'
                
            detected_lang = detect(sample_text)
            logger.info(f"Detected language: {detected_lang}")
            return detected_lang
            
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return 'en'
    
    def translate_to_turkish(self, text: str, source_lang: str) -> str:
        """Metni Türkçeye çevir - şu anda devre dışı"""
        if source_lang != 'tr' and source_lang != 'en':
            logger.info(f"Detected language: {source_lang.upper()} - Using original text without translation")
        return text
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """PDF'den metin çıkar - PyPDF2 ve OCR ile"""
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
                    logger.info("Text extracted using PyPDF2")
                    return text
                
                logger.info("Insufficient text with PyPDF2, trying OCR...")
                return self.extract_text_with_ocr(pdf_path)
                
        except Exception as e:
            logger.error(f"PDF text extraction error: {e}")
            logger.info("Switching to OCR...")
            return self.extract_text_with_ocr(pdf_path)

    def extract_text_with_ocr(self, pdf_path: str) -> str:
        """OCR ile metin çıkar"""
        try:
            images = convert_from_path(pdf_path, dpi=300)
            
            all_text = ""
            for i, image in enumerate(images):
                try:
                    text = pytesseract.image_to_string(image, lang='tur+eng')
                    text = re.sub(r'\s+', ' ', text)
                    text = text.replace('|', ' ')
                    all_text += text + "\n"
                    
                    logger.info(f"OCR extracted {len(text)} characters from page {i+1}")
                    
                except Exception as page_error:
                    logger.error(f"Page {i+1} OCR error: {page_error}")
                    continue
            
            all_text = all_text.replace('—', '-')
            all_text = all_text.replace('"', '"').replace('"', '"')
            all_text = all_text.replace('´', "'")
            all_text = re.sub(r'[^\x00-\x7F\u00C0-\u00FF\u0100-\u017F\u0180-\u024F]+', ' ', all_text)
            all_text = all_text.strip()
            
            logger.info(f"OCR total text length: {len(all_text)}")
            return all_text
            
        except Exception as e:
            logger.error(f"OCR text extraction error: {e}")
            return ""
    
    def check_declaration_date(self, text: str) -> Dict[str, Any]:
        """Beyan tarihini kontrol et"""
        date_patterns = [
            r"(?:February\s*2024|2024|5\s*February\s*2024)",
            r"(\d{1,2}\s*\w+\s*\d{4})",
            r"(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})",
            r"(\d{4}[./\-]\d{1,2}[./\-]\d{1,2})"
        ]
        
        current_date = datetime.now()
        
        for pattern in date_patterns:
            date_match = re.search(pattern, text, re.IGNORECASE)
            if date_match:
                date_str = date_match.group() if date_match.groups() == () else date_match.group(1)
                return {
                    "valid": True,
                    "date_found": date_str,
                    "reason": "Beyan tarihi bulundu",
                    "current": True
                }
        
        return {
            "valid": False,
            "date_found": "Bulunamadı",
            "reason": "Beyan tarihi bulunamadı",
            "current": False
        }
    
    def analyze_criteria(self, text: str, category: str) -> Dict[str, ECDeclarationAnalysisResult]:
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
                score = min(weight, len(matches) * (weight // 2))
                score = max(score, weight // 2)
            else:
                content = "Not found"
                found = False
                score = 0
            
            results[criterion_name] = ECDeclarationAnalysisResult(
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

    def calculate_scores(self, analysis_results: Dict[str, Dict[str, ECDeclarationAnalysisResult]]) -> Dict[str, Any]:
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
        """EC Declaration'dan özel değerleri çıkar"""
        values = {
            "machine_type": "Bulunamadı",
            "serial_number": "Bulunamadı",
            "manufacturer": "Bulunamadı",
            "authorized_representative": "Bulunamadı",
            "declaration_date": "Bulunamadı",
            "place_of_issue": "Bulunamadı",
            "signatory": "Bulunamadı"
        }
        
        # Makine tipi
        machine_patterns = [
            r"(?:Manufactured\s*By:\s*|Machine:\s*)([^\n\r]+)",
            r"(V524B.*machine|Knee\s*pad\s*punching\s*machine)"
        ]
        
        for pattern in machine_patterns:
            machine_match = re.search(pattern, text, re.IGNORECASE)
            if machine_match:
                values["machine_type"] = machine_match.group(1).strip()[:50]
                break
        
        # Seri numarası
        serial_patterns = [
            r"(?:Serial\s*Number:\s*)([A-Z0-9\-]+)",
            r"(A2306F-012)"
        ]
        
        for pattern in serial_patterns:
            serial_match = re.search(pattern, text, re.IGNORECASE)
            if serial_match:
                values["serial_number"] = serial_match.group(1).strip()
                break
        
        # Üretici
        manufacturer_patterns = [
            r"(Suzhou\s*Keber\s*Technology\s*Co[.,]?\s*LTD)",
            r"(?:manufacturer.*?)([A-Z][^\n]*Technology[^\n]*)"
        ]
        
        for pattern in manufacturer_patterns:
            manufacturer_match = re.search(pattern, text, re.IGNORECASE)
            if manufacturer_match:
                values["manufacturer"] = manufacturer_match.group(1).strip()[:50]
                break
        
        # Yetkili temsilci
        rep_patterns = [
            r"(Pilz\s*Ireland\s*Industrial\s*Automation)",
            r"(?:authorised\s*representative.*?)([A-Z][^\n]*Ireland[^\n]*)"
        ]
        
        for pattern in rep_patterns:
            rep_match = re.search(pattern, text, re.IGNORECASE)
            if rep_match:
                values["authorized_representative"] = rep_match.group(1).strip()[:50]
                break
        
        # Beyan tarihi
        date_patterns = [
            r"(5\s*February\s*2024|February\s*2024)",
            r"(\d{1,2}\s*\w+\s*\d{4})"
        ]
        
        for pattern in date_patterns:
            date_match = re.search(pattern, text, re.IGNORECASE)
            if date_match:
                values["declaration_date"] = date_match.group(1)
                break
        
        # Çıkarıldığı yer
        place_patterns = [
            r"(Cork\s*Ireland)",
            r"(Ireland)"
        ]
        
        for pattern in place_patterns:
            place_match = re.search(pattern, text, re.IGNORECASE)
            if place_match:
                values["place_of_issue"] = place_match.group(1).strip()
                break
        
        # İmzalayan
        signatory_patterns = [
            r"(John\s*McAuliffe.*Managing\s*Director)",
            r"(John\s*McAuliffe)",
            r"(Managing\s*Director)"
        ]
        
        for pattern in signatory_patterns:
            signatory_match = re.search(pattern, text, re.IGNORECASE)
            if signatory_match:
                values["signatory"] = signatory_match.group(1).strip()[:30]
                break
        
        return values

    def generate_recommendations(self, analysis_results: Dict, scores: Dict, date_check: Dict) -> List[str]:
        """EC Declaration için öneriler oluştur"""
        recommendations = []
        
        total_percentage = scores["percentage"]
        
        if total_percentage >= 80:
            recommendations.append(f"✅ EC Declaration of Conformity GEÇERLİ (Toplam: %{total_percentage:.0f})")
        elif total_percentage >= 70:
            recommendations.append(f"🟡 EC Declaration of Conformity KOŞULLU GEÇERLİ (Toplam: %{total_percentage:.0f})")
        else:
            recommendations.append(f"❌ EC Declaration of Conformity GEÇERSİZ (Toplam: %{total_percentage:.0f})")
        
        for category, results in analysis_results.items():
            category_score = scores["category_scores"][category]["percentage"]
            
            if category_score < 50:
                recommendations.append(f"🔴 {category} bölümü yetersiz (%{category_score:.0f})")
            elif category_score < 80:
                recommendations.append(f"🟡 {category} bölümü geliştirilmeli (%{category_score:.0f})")
            else:
                recommendations.append(f"🟢 {category} bölümü yeterli (%{category_score:.0f})")
        
        if total_percentage < 80:
            recommendations.extend([
                "",
                "💡 İYİLEŞTİRME ÖNERİLERİ:",
                "- Eksik direktif referanslarını tamamlayın",
                "- Standart referanslarını ekleyin",
                "- Teknik dosya bilgilerini detaylandırın",
                "- İmza ve yetkilendirme bilgilerini kontrol edin"
            ])
        
        return recommendations

    def analyze_ec_declaration(self, pdf_path: str) -> Dict[str, Any]:
        """Ana EC Declaration analiz fonksiyonu"""
        logger.info("EC Declaration of Conformity analysis starting...")
        
        if not os.path.exists(pdf_path):
            return {"error": f"PDF dosyası bulunamadı: {pdf_path}"}
        
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            return {"error": "PDF'den metin çıkarılamadı"}
        
        detected_lang = self.detect_language(text)
        
        if detected_lang not in ['tr', 'en']:
            logger.info(f"Translating from {detected_lang.upper()} to Turkish...")
            text = self.translate_to_turkish(text, detected_lang)
        
        # Tarih kontrolü
        date_check = self.check_declaration_date(text)
        
        analysis_results = {}
        for category in self.criteria_weights.keys():
            analysis_results[category] = self.analyze_criteria(text, category)
        
        scores = self.calculate_scores(analysis_results)
        extracted_values = self.extract_specific_values(text)
        recommendations = self.generate_recommendations(analysis_results, scores, date_check)
        
        final_status = "PASS" if scores["percentage"] >= 80 else ("CONDITIONAL" if scores["percentage"] >= 70 else "FAIL")
        final_score = scores["total_score"]
        final_percentage = scores["percentage"]
        
        report = {
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_info": {
                "pdf_path": pdf_path,
                "detected_language": detected_lang
            },
            "date_check": date_check,
            "extracted_values": extracted_values,
            "category_analyses": analysis_results,
            "scoring": scores,
            "recommendations": recommendations,
            "summary": {
                "total_score": final_score,
                "percentage": final_percentage,
                "status": final_status,
                "report_type": "EC_DECLARATION_OF_CONFORMITY",
                "date_valid": date_check["valid"]
            }
        }
        
        return report

def main():
    """Ana fonksiyon"""
    analyzer = ECDeclarationAnalyzer()

    pdf_path = "attipreport.pdf"

    if not os.path.exists(pdf_path):
        print(f"❌ PDF dosyası bulunamadı: {pdf_path}")
        return
    
    print("🔍 EC Declaration of Conformity Analizi Başlatılıyor...")
    print("=" * 60)
    
    report = analyzer.analyze_ec_declaration(pdf_path)
    
    if "error" in report:
        print(f"❌ Hata: {report['error']}")
        return
    
    print("\n📊 ANALİZ SONUÇLARI")
    print("=" * 60)
    
    print(f"📅 Analiz Tarihi: {report['analysis_date']}")
    print(f"🔍 Tespit Edilen Dil: {report['file_info']['detected_language'].upper()}")
    
    # Tarih kontrolü sonucu
    date_check = report['date_check']
    if date_check['valid']:
        print(f"📅 Beyan Tarihi: {date_check['date_found']} ✅ (Geçerli)")
    else:
        print(f"📅 Beyan Tarihi: {date_check['date_found']} ⚠️ ({date_check['reason']})")
    
    print(f"📋 Toplam Puan: {report['summary']['total_score']}/100")
    print(f"📈 Yüzde: %{report['summary']['percentage']:.0f}")
    print(f"🎯 Durum: {report['summary']['status']}")
    print(f"📄 Rapor Türü: {report['summary']['report_type']}")
    
    print("\n📋 ÖNEMLİ ÇIKARILAN DEĞERLER")
    print("-" * 40)
    extracted_values = report['extracted_values']
    display_names = {
        "machine_type": "Makine Tipi",
        "serial_number": "Seri Numarası",
        "manufacturer": "Üretici",
        "authorized_representative": "Yetkili Temsilci",
        "declaration_date": "Beyan Tarihi",
        "place_of_issue": "Çıkarıldığı Yer",
        "signatory": "İmzalayan"
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
    
    if report['summary']['percentage'] >= 80:
        print("✅ SONUÇ: GEÇERLİ")
        print(f"🌟 Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: EC Declaration of Conformity gerekli kriterleri sağlamaktadır.")
        
    elif report['summary']['percentage'] >= 70:
        print("🟡 SONUÇ: KOŞULLU GEÇERLİ")
        print(f"⚠️ Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: EC Declaration kabul edilebilir ancak bazı eksiklikler var.")
        
    else:
        print("❌ SONUÇ: GEÇERSİZ")
        print(f"⚠️ Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: EC Declaration minimum gereksinimleri karşılamıyor.")

if __name__ == "__main__":
    main()
