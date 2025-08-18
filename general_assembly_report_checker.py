#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
General Assembly Report Checker
Created for analyzing general assembly and installation reports from various companies
Supports both Turkish and English reports with OCR capabilities
"""

import PyPDF2
import pytesseract
from pdf2image import convert_from_path
import re
import logging
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from datetime import datetime
import os
from langdetect import detect

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@dataclass
class AssemblyAnalysisResult:
    """Data class for assembly analysis results"""
    criteria_name: str
    found: bool
    content: str
    score: int
    max_score: int
    details: Dict[str, Any]

class GeneralAssemblyReportAnalyzer:
    """Analyzer for general assembly and installation reports"""
    
    def __init__(self):
        logging.info("General Assembly Report analysis system starting...")
        
        # Scoring weights for each category (total = 100)
        self.criteria_weights = {
            "Proje Bilgileri": 20,        # Project Information
            "Montaj Detayları": 25,       # Assembly Details  
            "Test ve Kontroller": 20,     # Tests and Controls
            "Güvenlik ve Uyumluluk": 15,  # Safety and Compliance
            "Dokümantasyon": 10,          # Documentation
            "Onay ve İmzalar": 10         # Approvals and Signatures
        }
        
        # Criteria details with patterns for multi-company support
        self.criteria_details = {
            "Proje Bilgileri": {
                "proje_adi": {"pattern": r"(?:proje|project|sistem|system|makine|machine|installation|montaj)\s*(?:adı|name|ismi|başlığı|title)", "weight": 2},
                "proje_no": {"pattern": r"(?:proje|project|sistem|machine|makine)\s*(?:no|number|kodu|code|numarası)", "weight": 2},
                "tarih": {"pattern": r"(?:tarih|date|montaj tarihi|installation date|proje tarihi|project date)", "weight": 2},
                "lokasyon": {"pattern": r"(?:lokasyon|location|adres|address|tesis|facility|alan|site|yer)", "weight": 2},
                "musteri": {"pattern": r"(?:müşteri|customer|client|firma|company|işveren|owner)", "weight": 2}
            },
            "Montaj Detayları": {
                "montaj_plani": {"pattern": r"(?:montaj planı|assembly plan|installation plan|montaj şeması|layout|yerleşim)", "weight": 3},
                "malzeme_listesi": {"pattern": r"(?:malzeme|material|component|parça|ekipman|equipment|liste|list)", "weight": 3},
                "montaj_adimlari": {"pattern": r"(?:montaj adımları|assembly steps|installation steps|prosedür|procedure|method)", "weight": 3},
                "baglanti_detaylari": {"pattern": r"(?:bağlantı|connection|wiring|kablolama|electrical|elektrik|mekanik|mechanical)", "weight": 3},
                "ayar_kalibrasyonu": {"pattern": r"(?:ayar|adjustment|kalibrasyon|calibration|setting|parametreler|parameters)", "weight": 3}
            },
            "Test ve Kontroller": {
                "fonksiyonel_test": {"pattern": r"(?:fonksiyonel test|functional test|çalışma testi|operation test|performance)", "weight": 3},
                "elektrik_testleri": {"pattern": r"(?:elektrik|electrical|elektriksel|continuity|insulation|resistance|voltage)", "weight": 3},
                "guvenlik_testleri": {"pattern": r"(?:güvenlik|safety|emniyet|security|koruma|protection|test)", "weight": 3},
                "performans_testi": {"pattern": r"(?:performans|performance|verimlilik|efficiency|kapasite|capacity)", "weight": 3},
                "son_kontrol": {"pattern": r"(?:son kontrol|final check|final inspection|teslim|delivery|acceptance)", "weight": 2}
            },
            "Güvenlik ve Uyumluluk": {
                "ce_uyumlulugu": {"pattern": r"(?:CE|ce|uyumluluk|compliance|conformity|standard|norm)", "weight": 3},
                "guvenlik_onlemleri": {"pattern": r"(?:güvenlik önlemleri|safety measures|koruma|protection|emniyet|precaution)", "weight": 3},
                "risk_analizi": {"pattern": r"(?:risk|tehlike|danger|hazard|analiz|analysis|değerlendirme|assessment)", "weight": 3},
                "standartlar": {"pattern": r"(?:standart|standard|norm|regulation|yönetmelik|directive|direktif)", "weight": 3}
            },
            "Dokümantasyon": {
                "teknik_cizimler": {"pattern": r"(?:teknik çizim|technical drawing|şema|schema|diagram|plan|layout)", "weight": 2},
                "kullanim_kilavuzu": {"pattern": r"(?:kullanım kılavuzu|user manual|operation manual|işletme|maintenance)", "weight": 2},
                "bakim_plani": {"pattern": r"(?:bakım|maintenance|servis|service|preventive|koruyucu)", "weight": 2},
                "yedek_parca": {"pattern": r"(?:yedek parça|spare parts|replacement|değişim|parça listesi)", "weight": 2}
            },
            "Onay ve İmzalar": {
                "muhendis_onay": {"pattern": r"(?:mühendis|engineer|sorumlu|responsible|onay|approval|imza|signature)", "weight": 2},
                "musteri_kabulü": {"pattern": r"(?:müşteri kabulü|customer acceptance|teslim|delivery|kabul|approval)", "weight": 2},
                "kalite_kontrol": {"pattern": r"(?:kalite kontrol|quality control|QC|inspection|kontrol|denetim)", "weight": 2},
                "belgelendirme": {"pattern": r"(?:belge|certificate|certification|sertifika|document|onay)", "weight": 2}
            }
        }
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF using PyPDF2 and OCR fallback"""
        text = ""
        
        try:
            # First try PyPDF2
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    text += page.extract_text()
            
            logging.info(f"PyPDF2 extracted {len(text)} characters")
            
            # If PyPDF2 gives insufficient text, use OCR
            if len(text.strip()) < 100:
                logging.info("Insufficient text with PyPDF2, trying OCR...")
                
                pages = convert_from_path(pdf_path, dpi=200)
                ocr_text = ""
                
                for i, page in enumerate(pages, 1):
                    try:
                        page_text = pytesseract.image_to_string(page, lang='tur+eng')
                        ocr_text += page_text + "\n"
                        logging.info(f"OCR extracted {len(page_text)} characters from page {i}")
                    except Exception as e:
                        logging.warning(f"OCR failed for page {i}: {e}")
                        continue
                
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    logging.info(f"OCR total text length: {len(text)}")
            
        except Exception as e:
            logging.error(f"Error extracting text: {e}")
            raise
        
        return text
    
    def detect_language(self, text: str) -> str:
        """Detect document language"""
        try:
            if len(text.strip()) < 50:
                return "tr"  # Default to Turkish
            return detect(text)
        except:
            return "tr"
    
    def analyze_criteria(self, text: str, category: str) -> Dict[str, AssemblyAnalysisResult]:
        """Analyze criteria for a specific category"""
        results = {}
        criteria = self.criteria_details.get(category, {})
        
        for criterion_name, criterion_data in criteria.items():
            pattern = criterion_data["pattern"]
            weight = criterion_data["weight"]
            
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            
            if matches:
                content = f"Found: {str(matches[:3])}"
                found = True
                score = weight  # Full points for found criteria
            else:
                content = "Not found"
                found = False
                score = 0
            
            results[criterion_name] = AssemblyAnalysisResult(
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
    
    def calculate_scores(self, analysis_results: Dict[str, Dict[str, AssemblyAnalysisResult]]) -> Dict[str, Any]:
        """Calculate scoring for all categories"""
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
        """Extract specific values from assembly report"""
        values = {
            "project_name": "Bulunamadı",
            "project_number": "Bulunamadı", 
            "installation_date": "Bulunamadı",
            "customer_name": "Bulunamadı",
            "location": "Bulunamadı",
            "responsible_engineer": "Bulunamadı",
            "equipment_list": "Bulunamadı",
            "total_pages": "Bulunamadı"
        }
        
        # Project name
        project_patterns = [
            r"(?:Proje|Project|Sistem)\s*(?:Adı|Name|İsmi)?\s*[:\-]?\s*([A-Za-zÇŞİĞÜÖıçşığüö0-9\s\-\.]{5,50})",
            r"(?:Machine|Makine|Equipment)\s*(?:Name|İsmi|Adı)?\s*[:\-]?\s*([A-Za-zÇŞİĞÜÖıçşığüö0-9\s\-\.]{5,50})"
        ]
        
        for pattern in project_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                values["project_name"] = match.group(1).strip()
                break
        
        # Project number
        number_patterns = [
            r"(?:Proje|Project|Job|İş)\s*(?:No|Number|Numarası)?\s*[:\-]?\s*([A-Z0-9\-\.]{3,20})",
            r"(?:M|P|J)[\-]?(\d{4,8})"
        ]
        
        for pattern in number_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                values["project_number"] = match.group(1).strip()
                break
        
        # Date
        date_patterns = [
            r"(?:Tarih|Date|Montaj Tarihi)\s*[:\-]?\s*(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4})",
            r"(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4})"
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                values["installation_date"] = match.group(1).strip()
                break
        
        # Customer name  
        customer_patterns = [
            r"(?:Müşteri|Customer|Client|Firma)\s*[:\-]?\s*([A-Za-zÇŞİĞÜÖıçşığüö\s\.]{5,50})",
            r"(?:Company|Şirket)\s*[:\-]?\s*([A-Za-zÇŞİĞÜÖıçşığüö\s\.]{5,50})"
        ]
        
        for pattern in customer_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                values["customer_name"] = match.group(1).strip()
                break
        
        return values
    
    def generate_recommendations(self, analysis_results: Dict[str, Dict[str, AssemblyAnalysisResult]], 
                               scores: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        # Check each category performance
        for category, score_data in scores["category_scores"].items():
            if score_data["percentage"] < 50:
                recommendations.append(f"⚠️ {category} kategorisinde eksiklikler tespit edildi (%{score_data['percentage']:.0f})")
            elif score_data["percentage"] < 70:
                recommendations.append(f"📝 {category} kategorisi geliştirilebilir (%{score_data['percentage']:.0f})")
        
        # Specific recommendations based on missing criteria
        missing_critical = []
        for category, results in analysis_results.items():
            for criterion_name, result in results.items():
                if not result.found and result.max_score >= 3:  # Critical criteria
                    missing_critical.append(f"{category}: {criterion_name}")
        
        if missing_critical:
            recommendations.append("🔍 Eksik kritik kriterler:")
            for item in missing_critical[:5]:  # Show top 5
                recommendations.append(f"  • {item}")
        
        # General recommendations
        total_percentage = scores["percentage"]
        if total_percentage >= 80:
            recommendations.append("✅ Genel montaj raporu yüksek kalitede ve standartlara uygun")
        elif total_percentage >= 70:
            recommendations.append("📋 Genel montaj raporu kabul edilebilir seviyede")
        elif total_percentage >= 50:
            recommendations.append("⚠️ Genel montaj raporu minimum gereksinimleri karşılıyor ancak iyileştirme gerekli")
        else:
            recommendations.append("❌ Genel montaj raporu yetersiz, kapsamlı revizyon gerekli")
        
        return recommendations
    
    def analyze_assembly_report(self, pdf_path: str) -> Dict[str, Any]:
        """Main analysis function for assembly reports"""
        logging.info("General Assembly Report analysis starting...")
        
        try:
            # Extract text
            text = self.extract_text_from_pdf(pdf_path)
            
            if len(text.strip()) < 50:
                return {
                    "error": "PDF'den yeterli metin çıkarılamadı. Dosya bozuk olabilir veya sadece resim içeriyor olabilir.",
                    "text_length": len(text)
                }
            
            # Detect language
            detected_language = self.detect_language(text)
            logging.info(f"Detected language: {detected_language}")
            
            # Extract specific values
            extracted_values = self.extract_specific_values(text)
            
            # Analyze each category
            category_analyses = {}
            for category in self.criteria_weights.keys():
                category_analyses[category] = self.analyze_criteria(text, category)
            
            # Calculate scores
            scoring = self.calculate_scores(category_analyses)
            
            # Generate recommendations
            recommendations = self.generate_recommendations(category_analyses, scoring)
            
            # Determine overall status
            percentage = scoring["percentage"]
            if percentage >= 70:
                status = "PASS"
                status_tr = "GEÇERLİ"
            elif percentage >= 50:
                status = "CONDITIONAL"
                status_tr = "KOŞULLU"
            else:
                status = "FAIL"
                status_tr = "YETERSİZ"
            
            return {
                "analysis_date": datetime.now().isoformat(),
                "file_info": {
                    "filename": os.path.basename(pdf_path),
                    "text_length": len(text),
                    "detected_language": detected_language
                },
                "extracted_values": extracted_values,
                "category_analyses": category_analyses,
                "scoring": scoring,
                "recommendations": recommendations,
                "summary": {
                    "total_score": scoring["total_score"],
                    "percentage": percentage,
                    "status": status,
                    "status_tr": status_tr,
                    "report_type": "General Assembly Report"
                }
            }
            
        except Exception as e:
            logging.error(f"Analysis error: {e}")
            return {
                "error": f"Analiz sırasında hata oluştu: {str(e)}",
                "analysis_date": datetime.now().isoformat()
            }

def print_analysis_report(report: Dict[str, Any]):
    """Print formatted analysis report"""
    if "error" in report:
        print(f"❌ Hata: {report['error']}")
        return
    
    print("\n📊 GENEL MONTAJ RAPORU ANALİZİ")
    print("=" * 60)
    
    print(f"📅 Analiz Tarihi: {report['analysis_date']}")
    print(f"🔍 Tespit Edilen Dil: {report['file_info']['detected_language'].upper()}")
    
    print(f"📋 Toplam Puan: {report['summary']['total_score']}/100")
    print(f"📈 Yüzde: %{report['summary']['percentage']:.0f}")
    print(f"🎯 Durum: {report['summary']['status_tr']}")
    print(f"📄 Rapor Türü: {report['summary']['report_type']}")
    
    print("\n📋 ÇIKARILAN DEĞERLER")
    print("-" * 40)
    extracted_values = report['extracted_values']
    display_names = {
        "project_name": "Proje Adı",
        "project_number": "Proje No",
        "installation_date": "Montaj Tarihi",
        "customer_name": "Müşteri",
        "location": "Lokasyon",
        "responsible_engineer": "Sorumlu Mühendis",
        "equipment_list": "Ekipman Listesi"
    }
    
    for key, value in extracted_values.items():
        if key in display_names:
            print(f"{display_names[key]}: {value}")
    
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
        print("📝 Değerlendirme: Genel montaj raporu gerekli kriterleri sağlamaktadır.")
        
    elif report['summary']['percentage'] >= 50:
        print("🟡 SONUÇ: KOŞULLU")
        print(f"⚠️ Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: Genel montaj raporu kabul edilebilir ancak bazı eksiklikler var.")
        
    else:
        print("❌ SONUÇ: YETERSİZ")
        print(f"⚠️ Toplam Başarı: %{report['summary']['percentage']:.0f}")
        print("📝 Değerlendirme: Genel montaj raporu minimum gereksinimleri karşılamıyor.")

def main():
    """Main function for command line usage"""
    import sys
    
    if len(sys.argv) != 2:
        print("Kullanım: python general_assembly_report_checker.py <pdf_dosyasi>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    if not os.path.exists(pdf_path):
        print(f"❌ Dosya bulunamadı: {pdf_path}")
        sys.exit(1)
    
    analyzer = GeneralAssemblyReportAnalyzer()
    report = analyzer.analyze_assembly_report(pdf_path)
    print_analysis_report(report)

if __name__ == "__main__":
    main()
