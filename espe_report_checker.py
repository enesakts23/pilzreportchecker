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

# Logging konfigürasyonu
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ESPECriteria:
    """ESPE rapor kriterleri veri sınıfı"""
    genel_rapor_bilgileri: Dict[str, Any]
    koruma_cihazi_bilgileri: Dict[str, Any]
    makine_durus_performansi: Dict[str, Any]
    guvenlik_mesafesi_hesabi: Dict[str, Any]
    gorsel_teknik_dokumantasyon: Dict[str, Any]
    sonuc_oneriler: Dict[str, Any]

@dataclass
class ESPEAnalysisResult:
    """ESPE analiz sonucu veri sınıfı"""
    criteria_name: str
    found: bool
    content: str
    score: int
    max_score: int
    details: Dict[str, Any]

class ESPEReportAnalyzer:
    """ESPE rapor analiz sınıfı"""
    
    def __init__(self):
        self.criteria_weights = {
            "Genel Rapor Bilgileri": 15,
            "Koruma Cihazı (ESPE) Bilgileri": 15,
            "Makine Duruş Performansı Ölçümü": 25,
            "Güvenlik Mesafesi Hesabı": 25,
            "Görsel ve Teknik Dökümantasyon": 10,
            "Sonuç ve Öneriler": 10
        }
        
        self.criteria_details = {
            "Genel Rapor Bilgileri": {
                "proje_adi_numarasi": {"pattern": r"(?:Proje\s*No?\s*[:=]\s*|C\d{2}\.\d{3})", "weight": 3},
                "olcum_tarihi": {"pattern": r"(?:Ölçüm\s*Tarihi\s*[:=]\s*)?(\d{2}[./]\d{2}[./]\d{4})", "weight": 3},
                "rapor_tarihi": {"pattern": r"(?:Rapor\s*)?Tarihi?\s*[:=]\s*(\d{2}[./]\d{2}[./]\d{4})", "weight": 2},
                "makine_adi": {"pattern": r"(?:Makine\s*Ad[ıi]\s*[:=]\s*|Simple\s*Leak\s*Test|GPF\s*Line)", "weight": 3},
                "hat_bolge": {"pattern": r"(?:Hat\s*/\s*Bölge\s*Ad[ıi]\s*[:=]\s*|GPF\s*Line)", "weight": 2},
                "olcum_yapan": {"pattern": r"(?:Hazırlayan|Ölçümü\s*Yapan|Batuhan\s*Emek|Burak\s*Ateş)", "weight": 2}
            },
            "Koruma Cihazı (ESPE) Bilgileri": {
                "cihaz_tipi": {"pattern": r"(?:Tipi?\s*[:=]?\s*|Işık\s*Perdesi|Light\s*Curtain)", "weight": 3},
                "marka_model": {"pattern": r"(?:Marka\s*[:=]?\s*|DataLogic\s*SAFEasy|DataLogic|SAFEasy)", "weight": 3},
                "kategori": {"pattern": r"(?:Ekipman\s*)?Kategorisi\s*[:=]\s*([^\n\r]+)", "weight": 2},
                "koruma_yuksekligi": {"pattern": r"(?:Koruma\s*Yüksekliği.*?(\d{4})|(\d{4})\s*\d{2})", "weight": 2},
                "cozunurluk": {"pattern": r"(?:Çözünürlük.*?(\d{2})|\d{4}\s*(\d{2}))", "weight": 3},
                "yaklasim_yonu": {"pattern": r"(?:Yaklaşım\s*Yönü|Dikey|Yatay|El\s*Koruma)", "weight": 2}
            },
            "Makine Duruş Performansı Ölçümü": {
                "durma_zamani_min": {"pattern": r"(?:Min\s*[:=]?\s*(\d+)|(\d{2,3})\s*\d{2,3}\s*\d{2})", "weight": 5},
                "durma_zamani_max": {"pattern": r"(?:Maks?\s*[:=]?\s*(\d+)|(?:124|112))", "weight": 5},
                "durma_mesafesi": {"pattern": r"(?:Durma\s*Mesafesi|230\s*mm|376\s*mm)", "weight": 5},
                "durma_zamani_ms": {"pattern": r"(?:Durma\s*Zamanı.*?ms|STT|\d{2,3}\s*ms)", "weight": 5},
                "performans_olcumu": {"pattern": r"(?:124|112|76|75)", "weight": 3},
                "tekrarlanabilirlik": {"pattern": r"(?:tekrarlanabilirlik|ölçüm|test)", "weight": 2}
            },
            "Güvenlik Mesafesi Hesabı": {
                "formula_s": {"pattern": r"(?:S\s*=\s*\([^)]+\)|S\s*=\s*\(2000\s*x\s*T\)|S\s*=\s*\(K\s*x\s*T\s*\))", "weight": 8},
                "formula_c": {"pattern": r"(?:C\s*=\s*8\s*x?\*?\s*\(\s*d\s*-\s*14\s*\)|C\s*=\s*8\s*x\s*\(\s*d\s*-\s*14\s*\))", "weight": 5},
                "k_sabiti": {"pattern": r"(?:K\s*[=:]\s*(\d{4})|K=2000|K=1600|2000\s*mm/s|1600\s*mm/s)", "weight": 4},
                "hesaplanan_mesafe": {"pattern": r"(?:S\s*=\s*(\d+)|376\s*mm|230\s*mm)", "weight": 4},
                "mevcut_mesafe": {"pattern": r"(?:Mevcut.*?Mesafe|230\s*mm)", "weight": 2},
                "uygunluk_durumu": {"pattern": r"(?:DURUM\s*[:=]?\s*|UYGUN|UYGUNSUZ)", "weight": 2}
            },
            "Görsel ve Teknik Dökümantasyon": {
                "makine_gorseli": {"pattern": r"(?:Görsel|Fotoğraf|Resim)", "weight": 5},
                "olcum_gorseli": {"pattern": r"ölçüm.*(?:görsel|fotoğraf)", "weight": 3},
                "isaretli_gosterim": {"pattern": r"işaretli.*gösterim", "weight": 2}
            },
            "Sonuç ve Öneriler": {
                "tehlike_tanimi": {"pattern": r"tehlikeli\s*hareket[^.]*([^.\n]+)", "weight": 3},
                "uygunluk_degerlendirme": {"pattern": r"(?:uygun|uygunsuz)", "weight": 2},
                "iyilestirme_onerileri": {"pattern": r"(?:öneri|iyileştir|gelişti)", "weight": 3},
                "standart_baglantisi": {"pattern": r"EN\s*ISO\s*13855", "weight": 2}
            }
        }
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """PDF'den metin çıkarma"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
        except Exception as e:
            logger.error(f"PDF okuma hatası: {e}")
            return ""
    
    def extract_text_from_docx(self, docx_path: str) -> str:
        """DOCX'den metin çıkarma"""
        try:
            doc = Document(docx_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            logger.error(f"DOCX okuma hatası: {e}")
            return ""
    
    def check_report_date_validity(self, text: str) -> Tuple[bool, str, str]:
        """Rapor tarihinin geçerliliğini kontrol etme"""
        date_patterns = [
            r"Ölçüm\s*Tarihi\s*[:=]\s*(\d{2}[./]\d{2}[./]\d{4})",
            r"(\d{2}[./]\d{2}[./]\d{4})"
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            if matches:
                date_str = matches[0]
                try:
                    # Tarih formatını normalize et
                    date_str = date_str.replace('.', '/').replace('-', '/')
                    report_date = datetime.strptime(date_str, '%d/%m/%Y')
                    one_year_ago = datetime.now() - timedelta(days=365)
                    
                    is_valid = report_date >= one_year_ago
                    return is_valid, date_str, f"Rapor tarihi: {date_str} {'(GEÇERLİ)' if is_valid else '(GEÇERSİZ - 1 yıldan eski)'}"
                except ValueError:
                    continue
        
        return False, "", "Rapor tarihi bulunamadı"
    
    def analyze_criteria(self, text: str, category: str) -> Dict[str, ESPEAnalysisResult]:
        """Belirli kategori kriterlerini analiz etme"""
        results = {}
        criteria = self.criteria_details.get(category, {})
        
        for criterion_name, criterion_data in criteria.items():
            pattern = criterion_data["pattern"]
            weight = criterion_data["weight"]
            
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            
            if matches:
                content = str(matches[0]) if len(matches) == 1 else str(matches)
                found = True
                score = weight
            else:
                # İkincil arama - daha genel pattern
                general_patterns = {
                    "proje_adi_numarasi": r"(C\d+\.\d+|Proje|Project)",
                    "makine_adi": r"(Simple\s*Leak\s*Test|Test|Makine)",
                    "cihaz_tipi": r"(Işık\s*Perdesi|Light\s*Curtain|ESPE)",
                    "marka_model": r"(DataLogic|SAFEasy|Pilz)",
                    "formula_s": r"(S\s*=|mesafe|distance)",
                    "tehlike_tanimi": r"(fikstür|fixture|hareket|movement)"
                }
                
                general_pattern = general_patterns.get(criterion_name)
                if general_pattern:
                    general_matches = re.findall(general_pattern, text, re.IGNORECASE)
                    if general_matches:
                        content = f"Genel eşleşme bulundu: {general_matches[0]}"
                        found = True
                        score = weight // 2  # Kısmi puan
                    else:
                        content = "Bulunamadı"
                        found = False
                        score = 0
                else:
                    content = "Bulunamadı"
                    found = False
                    score = 0
            
            results[criterion_name] = ESPEAnalysisResult(
                criteria_name=criterion_name,
                found=found,
                content=content,
                score=score,
                max_score=weight,
                details={"pattern_used": pattern, "matches_found": len(matches) if matches else 0}
            )
        
        return results
    
    def extract_specific_values(self, text: str) -> Dict[str, Any]:
        """Spesifik değerleri çıkarma"""
        values = {}
        
        # Önemli değerler için pattern'ler
        value_patterns = {
            "proje_no": r"(?:Proje\s*No\s*[:=]\s*|C\d{2}\.\d{3})",
            "olcum_tarihi": r"(?:Ölçüm\s*Tarihi\s*[:=]\s*)?(\d{2}[./]\d{2}[./]\d{4})",
            "makine_adi": r"(?:Makine\s*Ad[ıi]\s*[:=]\s*|Simple\s*Leak\s*Test)",
            "hat_bolge": r"(?:Hat\s*/\s*Bölge\s*Ad[ıi]\s*[:=]\s*|GPF\s*Line)",
            "marka": r"(?:DataLogic\s*SAFEasy|DataLogic|SAFEasy)",
            "model": r"(?:Model\s*[:=]?\s*|SAFEasy)",
            "koruma_yuksekligi": r"(?:1200|(\d{4})\s*30)",
            "cozunurluk": r"(?:30|1200\s*(\d{2}))",
            "durma_zamani_min": r"(?:Min\s*(\d+)|(?:76|75))",
            "durma_zamani_max": r"(?:Maks?\s*(\d+)|(?:124|112))",
            "mevcut_mesafe": r"(?:230\s*mm|(\d{3})\s*mm)",
            "hesaplanan_mesafe": r"(?:376\s*mm|S\s*=\s*(\d+))",
            "durum": r"(?:DURUM\s*|UYGUN|UYGUNSUZ)",
            "tehlikeli_hareket": r"(?:tehlikeli\s*hareket|fikstür\s*hareket|Makinenin\s*fikstür)",
            "k_sabiti": r"(?:K\s*=\s*(\d{4})|2000|1600)",
            "formula_s": r"(?:S\s*=\s*\([^)]+\)|S\s*=\s*\(2000\s*x\s*T\))",
            "formula_c": r"(?:C\s*=\s*8\s*x\s*\([^)]+\)|C\s*=\s*8\s*x\s*\(\s*d\s*-\s*14\s*\))",
            "en_iso_13855": r"(?:EN\s*ISO\s*13855|EN\s*ISO\s*14120|EN\s*ISO\s*13857)"
        }
        
        for key, pattern in value_patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                values[key] = matches[0].strip()
            else:
                values[key] = "Bulunamadı"
        
        return values
    
    def calculate_scores(self, analysis_results: Dict[str, Dict[str, ESPEAnalysisResult]]) -> Dict[str, Any]:
        """Puanları hesaplama"""
        category_scores = {}
        total_score = 0
        total_max_score = 100
        
        for category, results in analysis_results.items():
            category_max = self.criteria_weights[category]
            category_earned = sum(result.score for result in results.values())
            category_possible = sum(result.max_score for result in results.values())
            
            # Kategori puanını ağırlığa göre normalize et
            normalized_score = (category_earned / category_possible * category_max) if category_possible > 0 else 0
            
            category_scores[category] = {
                "earned": category_earned,
                "possible": category_possible,
                "normalized": round(normalized_score, 2),
                "max_weight": category_max,
                "percentage": round((category_earned / category_possible * 100), 2) if category_possible > 0 else 0
            }
            
            total_score += normalized_score
        
        return {
            "category_scores": category_scores,
            "total_score": round(total_score, 2),
            "total_max_score": total_max_score,
            "overall_percentage": round((total_score / total_max_score * 100), 2)
        }
    
    def generate_detailed_report(self, pdf_path: str, docx_path: str = None) -> Dict[str, Any]:
        """Detaylı rapor oluşturma"""
        logger.info("ESPE rapor analizi başlatılıyor...")
        
        # PDF'den metin çıkar
        pdf_text = self.extract_text_from_pdf(pdf_path)
        if not pdf_text:
            return {"error": "PDF okunamadı"}
        
        # Tarih geçerliliği kontrolü
        date_valid, date_str, date_message = self.check_report_date_validity(pdf_text)
        
        # Spesifik değerleri çıkar
        extracted_values = self.extract_specific_values(pdf_text)
        
        # Her kategori için analiz yap
        analysis_results = {}
        for category in self.criteria_weights.keys():
            analysis_results[category] = self.analyze_criteria(pdf_text, category)
        
        # Puanları hesapla
        scores = self.calculate_scores(analysis_results)
        
        # Öneriler oluştur
        recommendations = self.generate_recommendations(analysis_results, scores)
        
        report = {
            "analiz_tarihi": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dosya_bilgileri": {
                "pdf_path": pdf_path,
                "docx_path": docx_path
            },
            "tarih_gecerliligi": {
                "gecerli": date_valid,
                "tarih": date_str,
                "mesaj": date_message
            },
            "cikarilan_degerler": extracted_values,
            "kategori_analizleri": analysis_results,
            "puanlama": scores,
            "oneriler": recommendations,
            "ozet": {
                "toplam_puan": scores["total_score"],
                "yuzde": scores["overall_percentage"],
                "durum": "GEÇERLİ" if scores["overall_percentage"] >= 70 else "YETERSİZ",
                "tarih_durumu": "GEÇERLİ" if date_valid else "GEÇERSİZ"
            }
        }
        
        return report
    
    def generate_recommendations(self, analysis_results: Dict, scores: Dict) -> List[str]:
        """Öneriler oluşturma"""
        recommendations = []
        
        for category, results in analysis_results.items():
            category_score = scores["category_scores"][category]["percentage"]
            
            if category_score < 50:
                recommendations.append(f"❌ {category} bölümü yetersiz (%{category_score:.1f})")
                
                # Eksik kriterler
                missing_criteria = [name for name, result in results.items() if not result.found]
                if missing_criteria:
                    recommendations.append(f"  Eksik kriterler: {', '.join(missing_criteria)}")
            
            elif category_score < 80:
                recommendations.append(f"⚠️ {category} bölümü geliştirilmeli (%{category_score:.1f})")
            
            else:
                recommendations.append(f"✅ {category} bölümü yeterli (%{category_score:.1f})")
        
        # Genel öneriler
        if scores["overall_percentage"] < 70:
            recommendations.append("\n🚨 GENEL ÖNERİLER:")
            recommendations.append("- Rapor EN ISO 13855 standardına tam uyumlu hale getirilmelidir")
            recommendations.append("- Eksik bilgiler tamamlanmalıdır")
            recommendations.append("- Formül hesaplamaları detaylandırılmalıdır")
        
        return recommendations
    
    def save_report_to_excel(self, report: Dict, output_path: str):
        """Raporu Excel'e kaydetme"""
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Özet sayfa
            ozet_data = {
                'Kriter': ['Toplam Puan', 'Yüzde', 'Durum', 'Tarih Durumu'],
                'Değer': [
                    report['ozet']['toplam_puan'],
                    f"%{report['ozet']['yuzde']}",
                    report['ozet']['durum'],
                    report['ozet']['tarih_durumu']
                ]
            }
            pd.DataFrame(ozet_data).to_excel(writer, sheet_name='Özet', index=False)
            
            # Çıkarılan değerler
            values_data = []
            for key, value in report['cikarilan_degerler'].items():
                values_data.append({'Kriter': key, 'Değer': value})
            pd.DataFrame(values_data).to_excel(writer, sheet_name='Çıkarılan Değerler', index=False)
            
            # Kategori detayları
            for category, results in report['kategori_analizleri'].items():
                category_data = []
                for criterion, result in results.items():
                    category_data.append({
                        'Kriter': criterion,
                        'Bulundu': result.found,
                        'İçerik': result.content,
                        'Puan': result.score,
                        'Max Puan': result.max_score
                    })
                
                sheet_name = category[:31]  # Excel sheet name limit
                pd.DataFrame(category_data).to_excel(writer, sheet_name=sheet_name, index=False)
        
        logger.info(f"Rapor Excel dosyası kaydedildi: {output_path}")
    
    def save_report_to_json(self, report: Dict, output_path: str):
        """Raporu JSON'a kaydetme"""
        # ESPEAnalysisResult objelerini dict'e çevir
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
        
        logger.info(f"Rapor JSON dosyası kaydedildi: {output_path}")

def main():
    """Ana fonksiyon"""
    analyzer = ESPEReportAnalyzer()
    
    # Dosya yolları
    pdf_path = "C24.017 - ESPE - GPF Simple Leak Test.pdf"
    docx_path = "ESPE_Rapor_Kriterleri_Puanlama.docx"
    
    # Dosyaların varlığını kontrol et
    if not os.path.exists(pdf_path):
        print(f"❌ PDF dosyası bulunamadı: {pdf_path}")
        return
    
    print("🔍 ESPE Rapor Analizi Başlatılıyor...")
    print("=" * 60)
    
    # Analizi çalıştır
    report = analyzer.generate_detailed_report(pdf_path, docx_path)
    
    if "error" in report:
        print(f"❌ Hata: {report['error']}")
        return
    
    # Sonuçları göster
    print("\n📊 ANALİZ SONUÇLARI")
    print("=" * 60)
    
    print(f"📅 Analiz Tarihi: {report['analiz_tarihi']}")
    print(f"📋 Toplam Puan: {report['ozet']['toplam_puan']}/100")
    print(f"📈 Yüzde: %{report['ozet']['yuzde']}")
    print(f"🎯 Durum: {report['ozet']['durum']}")
    print(f"📆 Tarih Durumu: {report['ozet']['tarih_durumu']}")
    
    print(f"\n⚠️ Tarih Kontrolü: {report['tarih_gecerliligi']['mesaj']}")
    
    print("\n📋 ÖNEMLİ ÇIKARILAN DEĞERLER")
    print("-" * 40)
    important_values = ['proje_no', 'olcum_tarihi', 'makine_adi', 'marka', 'model', 
                       'mevcut_mesafe', 'hesaplanan_mesafe', 'durum', 'tehlikeli_hareket']
    
    for key in important_values:
        if key in report['cikarilan_degerler']:
            print(f"{key.replace('_', ' ').title()}: {report['cikarilan_degerler'][key]}")
    
    print("\n📊 KATEGORİ PUANLARI")
    print("-" * 40)
    for category, score_data in report['puanlama']['category_scores'].items():
        print(f"{category}: {score_data['normalized']}/{score_data['max_weight']} (%{score_data['percentage']:.1f})")
    
    print("\n💡 ÖNERİLER")
    print("-" * 40)
    for recommendation in report['oneriler']:
        print(recommendation)
    
    # Raporları kaydet
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_path = f"ESPE_Analiz_Raporu_{timestamp}.xlsx"
    json_path = f"ESPE_Analiz_Raporu_{timestamp}.json"
    
    analyzer.save_report_to_excel(report, excel_path)
    analyzer.save_report_to_json(report, json_path)
    
    print(f"\n💾 Raporlar kaydedildi:")
    print(f"   📊 Excel: {excel_path}")
    print(f"   📄 JSON: {json_path}")

if __name__ == "__main__":
    main()