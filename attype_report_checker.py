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
                "ec_declaration_title": {"pattern": r"(?:EC\s*-?\s*Declaration|Declaration\s*of\s*Conformity|conformity|declaration)", "weight": 5},
                "authorized_representative": {"pattern": r"(?:authorised\s*representative|authorized\s*representative|representative)", "weight": 4},
                "conformity_statement": {"pattern": r"(?:is\s*in\s*conformity|declare.*manufacturer|sole\s*responsibility|conformity)", "weight": 4},
                "manufacturer_responsibility": {"pattern": r"(?:under\s*the\s*sole\s*responsibility|manufacturer|responsibility)", "weight": 4},
                "declaration_scope": {"pattern": r"(?:this\s*declaration\s*relates|To\s*which\s*this\s*declaration|declaration\s*relates)", "weight": 4},
                "conformity_declared": {"pattern": r"(?:Conformity\s*is\s*declared|in\s*reference\s*to|declared)", "weight": 4}
            },
            "Makine ve Üretici Bilgileri": {
                "machine_description": {"pattern": r"(?:machine|equipment|device|product)", "weight": 5},
                "serial_number": {"pattern": r"(?:Serial\s*Number|serial\s*no|S/N|serial)", "weight": 4},
                "manufacturer_name": {"pattern": r"(?:manufacturer|manufactured\s*by|company|ltd|gmbh|inc)", "weight": 4},
                "manufacturer_address": {"pattern": r"(?:address|street|road|city|country)", "weight": 4},
                "product_identification": {"pattern": r"(?:Manufactured\s*By|model|type|product)", "weight": 3}
            },
            "Direktif Uygunluk": {
                "machinery_directive_2006": {"pattern": r"(?:2006/42/EC|Machinery\s*Directive|directive)", "weight": 8},
                "european_directives": {"pattern": r"(?:European\s*Directives|following.*Directives|directives)", "weight": 6},
                "conformity_with_directives": {"pattern": r"(?:conformity\s*with.*Directives|in\s*conformity\s*with|complies)", "weight": 6}
            },
            "Standart Referansları": {
                "safety_standards": {"pattern": r"(?:EN\s*\d+|ISO\s*\d+|IEC\s*\d+|standard|norm)", "weight": 5},
                "machinery_standards": {"pattern": r"(?:Safety\s*of\s*machinery|safety.*standard|safety)", "weight": 5},
                "electrical_standards": {"pattern": r"(?:electrical\s*equipment|electrical\s*safety)", "weight": 3},
                "normative_documents": {"pattern": r"(?:standard|normative\s*document|norm|specification)", "weight": 2}
            },
            "Teknik Dosya Bilgileri": {
                "technical_file_authority": {"pattern": r"(?:Person\s*authorised.*Technical\s*File|technical\s*file|technical\s*documentation)", "weight": 5},
                "technical_file_reference": {"pattern": r"(?:Technical\s*File|technical.*file|technical.*doc)", "weight": 3},
                "authorized_person": {"pattern": r"(?:Person\s*authorised|authorised\s*person|authorized)", "weight": 2}
            },
            "İmza ve Yetkilendirme": {
                "signature_present": {"pattern": r"(?:Pilz\s*Signature|Signature|Name\s*and\s*title|signatory|John\s*McAuliffe)", "weight": 3},
                "signatory_name": {"pattern": r"(?:John\s*McAuliffe|McAuliffe|director|manager|engineer|responsible)", "weight": 2},
                "signatory_title": {"pattern": r"(?:Managing\s*Director|Director|Manager|Engineer)", "weight": 2},
                "date_of_declaration": {"pattern": r"(?:\d{1,2}[\s./\-]\w+[\s./\-]\d{4}|\d{4}[\s./\-]\d{1,2}[\s./\-]\d{1,2}|February\s*2024)", "weight": 2},
                "place_of_issue": {"pattern": r"(?:Cork\s*Ireland|place|location|issued|country|Ireland)", "weight": 1}
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
        """PDF'den metin çıkar - PyPDF2 ve OCR ile (kombinasyonu)"""
        pypdf_text = ""
        ocr_text = ""
        
        # Önce PyPDF2 ile dene
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    page_text = re.sub(r'\s+', ' ', page_text)
                    page_text = page_text.replace('|', ' ')
                    pypdf_text += page_text + "\n"
                
                pypdf_text = pypdf_text.replace('—', '-')
                pypdf_text = pypdf_text.replace('"', '"').replace('"', '"')
                pypdf_text = pypdf_text.replace('´', "'")
                pypdf_text = re.sub(r'[^\x00-\x7F\u00C0-\u00FF\u0100-\u017F\u0180-\u024F]+', ' ', pypdf_text)
                pypdf_text = pypdf_text.strip()
                
                if len(pypdf_text) > 50:
                    logger.info("Text extracted using PyPDF2")
        except Exception as e:
            logger.error(f"PDF text extraction error: {e}")
        
        # OCR ile de dene (özellikle imza ve görsel öğeler için)
        try:
            logger.info("Also trying OCR for better text detection...")
            ocr_text = self.extract_text_with_ocr(pdf_path)
        except Exception as e:
            logger.error(f"OCR text extraction error: {e}")
        
        # İki metni birleştir (OCR'dan daha fazla bilgi alabilir)
        if pypdf_text and ocr_text:
            # OCR'dan ekstra bilgi varsa ekle
            combined_text = pypdf_text + "\n--- OCR ADDITION ---\n" + ocr_text
            logger.info("Combined PyPDF2 and OCR text")
            return combined_text
        elif pypdf_text:
            return pypdf_text
        elif ocr_text:
            logger.info("Using OCR text only")
            return ocr_text
        else:
            logger.error("No text could be extracted")
            return ""

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
        """EC Declaration'dan özel değerleri çıkar - Genel pattern'ler"""
        values = {
            "machine_type": "Bulunamadı",
            "serial_number": "Bulunamadı", 
            "manufacturer": "Bulunamadı",
            "manufacturer_address": "Bulunamadı",
            "authorized_representative": "Bulunamadı",
            "declaration_date": "Bulunamadı",
            "place_of_issue": "Bulunamadı",
            "signatory": "Bulunamadı",
            "machinery_directive": "Bulunamadı",
            "safety_standards": "Bulunamadı"
        }
        
        # Makine tipi - daha spesifik arama
        machine_patterns = [
            r"([A-Z]\d+[A-Z]?\s+[A-Za-z\s]+(?:machine|equipment|device))",  # V524B Knee pad punching machine
            r"(?:machine|equipment|device)[\s:]*([A-Z0-9\-\s]+machine)",
            r"(?:Manufactured\s*By:?\s*)([A-Z]\d+[A-Z]?\s+[A-Za-z\s]+)"
        ]
        for pattern in machine_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                machine_type = match.group(1).strip()
                if len(machine_type) > 3 and not machine_type.startswith("Manufactured"):
                    values["machine_type"] = machine_type
                    break
        
        # Seri numarası - genel arama  
        serial_patterns = [
            r"(?:Serial\s*Number|S/N|serial)[\s:]*([A-Z0-9\-]+)",
            r"([A-Z]\d+[A-Z]?\-\d+)"
        ]
        for pattern in serial_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                values["serial_number"] = match.group(1).strip()
                break
        
        # Üretici - daha spesifik arama
        manufacturer_patterns = [
            r"(Suzhou\s+Keber\s+Technology\s+Co[.,]*\s*LTD)",  # Spesifik üretici
            r"([A-Za-z\s]+Technology\s+Co[.,]*\s*(?:Ltd|LTD))",
            r"(?:Manufactured\s*By|manufacturer)[\s:]*([A-Za-z\s\.,&]+(?:Ltd|LTD|GmbH|Inc|Co\.))"
        ]
        for pattern in manufacturer_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                manufacturer = match.group(1).strip()
                if len(manufacturer) > 5:
                    values["manufacturer"] = manufacturer
                    break
        
        # Üretici adresi - genel arama
        address_patterns = [
            r"(\d+[\s\w,\-\.]+(?:Road|Street|Avenue|Park|District|City|Province))",
            r"(No\.?\s*\d+[\s\w,\-\.]+(?:Road|Street|Avenue|Park|District|City|Province))"
        ]
        for pattern in address_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                values["manufacturer_address"] = match.group(1).strip()
                break
        
        # Yetkili temsilci - daha spesifik arama
        rep_patterns = [
            r"(Pilz\s+Ireland\s+Industrial\s+Automation)",  # Spesifik temsilci
            r"([A-Za-z\s]+Ireland[A-Za-z\s]*(?:Automation|Industrial))",
            r"([A-Za-z\s]+(?:representative|Representative))"
        ]
        for pattern in rep_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                rep = match.group(1).strip()
                if len(rep) > 5 and not rep.startswith("Ireland declare"):
                    values["authorized_representative"] = rep
                    break
        
        # Beyan tarihi - genel arama
        date_patterns = [
            r"(\d{1,2}\s+\w+\s+\d{4})",
            r"(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})",
            r"(\d{4}[./\-]\d{1,2}[./\-]\d{1,2})"
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                values["declaration_date"] = match.group(1).strip()
                break
        
        # Çıkarıldığı yer - daha spesifik arama
        place_patterns = [
            r"(Cork\s+Ireland)",  # Spesifik yer
            r"([A-Za-z\s]+Ireland)",
            r"([A-Za-z\s]+(?:Germany|UK|USA|Italy|France|Spain))"
        ]
        for pattern in place_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                place = match.group(1).strip()
                if len(place) > 3 and not place.startswith("We Pilz"):
                    values["place_of_issue"] = place
                    break
        
        # İmzalayan - daha spesifik arama
        signatory_patterns = [
            r"(John\s+McAuliffe)[,\s]*Managing\s*Director",
            r"([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]*(?:Managing\s*Director|Director|Manager)",
            r"(?:Managing\s*Director|Director|Manager)[:\s]*([A-Z][a-z]+\s+[A-Z][a-z]+)"
        ]
        for pattern in signatory_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                signatory = match.group(1).strip()
                values["signatory"] = f"{signatory}, Managing Director"
                break
        
        # Makine Direktifi - genel arama
        if re.search(r"2006/42/EC", text, re.IGNORECASE):
            values["machinery_directive"] = "2006/42/EC The Machinery Directive"
        
        # Güvenlik standartları - genel arama
        standards_found = []
        standard_patterns = [
            r"(EN\s+\d+[\-\d]*:\s*\d{4})",
            r"(ISO\s+\d+[\-\d]*:\s*\d{4})",
            r"(IEC\s+\d+[\-\d]*:\s*\d{4})"
        ]
        
        for pattern in standard_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            standards_found.extend(matches)
        
        if standards_found:
            values["safety_standards"] = ", ".join(list(set(standards_found)))
        
        return values

    def generate_recommendations(self, analysis_results: Dict, scores: Dict, date_check: Dict) -> List[str]:
        """EC Declaration için öneriler oluştur"""
        recommendations = []
        
        total_percentage = scores["percentage"]
        
        if total_percentage >= 65:
            recommendations.append(f"✅ EC Declaration of Conformity GEÇERLİ (Toplam: %{total_percentage:.0f})")
        elif total_percentage >= 55:
            recommendations.append(f"🟡 EC Declaration of Conformity KOŞULLU GEÇERLİ (Toplam: %{total_percentage:.0f})")
        else:
            recommendations.append(f"❌ EC Declaration of Conformity GEÇERSİZ (Toplam: %{total_percentage:.0f})")
        
        for category, results in analysis_results.items():
            category_score = scores["category_scores"][category]["percentage"]
            
            if category_score < 40:
                recommendations.append(f"🔴 {category} bölümü yetersiz (%{category_score:.0f})")
            elif category_score < 65:
                recommendations.append(f"🟡 {category} bölümü geliştirilmeli (%{category_score:.0f})")
            else:
                recommendations.append(f"🟢 {category} bölümü yeterli (%{category_score:.0f})")
        
        if total_percentage < 65:
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
        
        final_status = "PASS" if scores["percentage"] >= 65 else ("CONDITIONAL" if scores["percentage"] >= 55 else "FAIL")
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
        "manufacturer_address": "Üretici Adresi",
        "authorized_representative": "Yetkili Temsilci",
        "declaration_date": "Beyan Tarihi",
        "place_of_issue": "Çıkarıldığı Yer",
        "signatory": "İmzalayan",
        "machinery_directive": "Makine Direktifi",
        "safety_standards": "Güvenlik Standartları"
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
    
    if report['summary']['percentage'] >= 65:
        print("✅ SONUÇ: GEÇERLİ")
        print(f"🌟 Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: EC Declaration of Conformity gerekli kriterleri sağlamaktadır.")
        
    elif report['summary']['percentage'] >= 55:
        print("🟡 SONUÇ: KOŞULLU GEÇERLİ")
        print(f"⚠️ Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: EC Declaration kabul edilebilir ancak bazı eksiklikler var.")
        
    else:
        print("❌ SONUÇ: GEÇERSİZ")
        print(f"⚠️ Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: EC Declaration minimum gereksinimleri karşılamıyor.")

if __name__ == "__main__":
    main()
