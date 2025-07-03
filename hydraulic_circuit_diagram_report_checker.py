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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class HidrolikCriteria:
    enerji_kaynagi: Dict[str, Any]
    hidrolik_semboller: Dict[str, Any]
    akis_yonu_baglanti: Dict[str, Any]
    sistem_bilgileri: Dict[str, Any]
    baslik_belgelendirme: Dict[str, Any]

@dataclass
class HidrolikAnalysisResult:
    criteria_name: str
    found: bool
    content: str
    score: int
    max_score: int
    details: Dict[str, Any]

class HidrolikDevreAnalyzer:
    
    def __init__(self):
        self.criteria_weights = {
            "Enerji Kaynağı": 25,
            "Hidrolik Semboller ve Bileşenler": 30,
            "Akış Yönü ve Bağlantı Hattı": 20,
            "Sistem Bilgileri ve Etiketler": 15,
            "Başlık ve Belgelendirme": 10
        }
        
        self.criteria_details = {
            "Enerji Kaynağı": {
                "basinc_yagi": {"pattern": r"(?:yağ|hydraulic|oil|basınç|pressure)", "weight": 8},
                "basinc_aralik": {"pattern": r"(?:80|100|120|180|200|300|350).*?(?:bar|Bar|BAR)", "weight": 8},
                "sivil_guc": {"pattern": r"(?:sıvı|liquid|hydraulic|hidrolik)", "weight": 5},
                "yuksek_basinc": {"pattern": r"(?:80|100|120|180|200|300|350).*?(?:bar|Bar|BAR)", "weight": 4}
            },
            "Hidrolik Semboller ve Bileşenler": {
                "pompa_sembol": {"pattern": r"(?:pompa|pump|40P1|40M1|P1|M1)", "weight": 5},
                "motor_sembol": {"pattern": r"(?:motor|Motor|40M1|M1)", "weight": 5},
                "silindir_sembol": {"pattern": r"(?:silindir|cylinder|piston|çift etkili|tek etkili)", "weight": 5},
                "basinc_valfi": {"pattern": r"(?:basınç|pressure|valve|valf|40R1|R1)", "weight": 5},
                "yon_kontrol_valfi": {"pattern": r"(?:4/2|4/3|3/2|DCV|yön kontrol|valve)", "weight": 5},
                "tank_sembol": {"pattern": r"(?:tank|Tank|400U1|U1|V=\s*40)", "weight": 3},
                "filtre_sembol": {"pattern": r"(?:filtre|filter|F1)", "weight": 2}
            },
            "Akış Yönü ve Bağlantı Hattı": {
                "cizgi_borular": {"pattern": r"(?:boru|pipe|hat|line|çizgi)", "weight": 5},
                "yon_oklari": {"pattern": r"(?:yön|direction|ok|arrow|akış)", "weight": 5},
                "pompa_cikis": {"pattern": r"(?:pompa.*çıkış|pump.*output|basınç hatt)", "weight": 5},
                "tank_donus": {"pattern": r"(?:tank.*dönüş|return|tahliye)", "weight": 3},
                "birlesim_nokta": {"pattern": r"(?:birleşim|junction|bağlantı|connection)", "weight": 2}
            },
            "Sistem Bilgileri ve Etiketler": {
                "bar_basinc": {"pattern": r"(?:80|100|120|180|200|300|350).*?(?:bar|Bar|BAR)", "weight": 4},
                "debi_bilgi": {"pattern": r"(?:cc/rev|cc/dakika|12.*?lt/dak|lt/min)", "weight": 3},
                "guc_bilgi": {"pattern": r"(?:3\s*kW|kW|HP|güç|power|1500.*?rpm)", "weight": 3},
                "tank_hacmi": {"pattern": r"(?:V=\s*40|40.*?LT|tank.*?hacmi)", "weight": 2},
                "yag_tipi": {"pattern": r"(?:yağ|oil|hydraulic|fluid)", "weight": 2},
                "motor_gucu": {"pattern": r"(?:3\s*kW|kW|1500.*?rpm|motor.*?güç)", "weight": 1}
            },
            "Başlık ve Belgelendirme": {
                "hydraulic_scheme": {"pattern": r"(?:HYDRAULIC|hydraulic|HİDROLİK|hidrolik)", "weight": 3},
                "data_sheet": {"pattern": r"(?:DATA\s*SHEET|data.*?sheet|veri.*?sayfası)", "weight": 2},
                "manifold_plan": {"pattern": r"(?:MANIFOLD\s*PLAN|manifold|kolektör)", "weight": 2},
                "cizim_standardi": {"pattern": r"(?:ISO\s*1219|standart|standard)", "weight": 2},
                "teknik_resim": {"pattern": r"(?:Teknik\s*Resim|technical.*?drawing)", "weight": 1}
            }
        }
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
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
        try:
            doc = Document(docx_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            logger.error(f"DOCX okuma hatası: {e}")
            return ""
    
    def check_hydraulic_validity(self, text: str) -> Tuple[bool, str]:
        hydraulic_indicators = [
            r"(?:HYDRAULIC|hydraulic|HİDROLİK|hidrolik)",
            r"(?:basınç|pressure|bar|Bar|BAR)",
            r"(?:pompa|pump|motor|silindir|cylinder)",
            r"(?:yağ|oil|hydraulic|fluid)",
            r"(?:DATA\s*SHEET.*HYDRAULIC|MANIFOLD\s*PLAN)"
        ]
        
        found_indicators = 0
        for pattern in hydraulic_indicators:
            if re.search(pattern, text, re.IGNORECASE):
                found_indicators += 1
        
        is_hydraulic = found_indicators >= 3
        confidence = (found_indicators / len(hydraulic_indicators)) * 100
        
        return is_hydraulic, f"Hidrolik devre güvenilirlik: %{confidence:.1f} ({found_indicators}/{len(hydraulic_indicators)} kriter)"
    
    def analyze_criteria(self, text: str, category: str) -> Dict[str, HidrolikAnalysisResult]:
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
                general_patterns = {
                    "basinc_yagi": r"(yağ|oil|hydraulic)",
                    "basinc_aralik": r"(\d{2,3}.*?bar|\d{2,3}.*?Bar)",
                    "pompa_sembol": r"(pompa|pump|P\d+)",
                    "motor_sembol": r"(motor|M\d+)",
                    "silindir_sembol": r"(silindir|cylinder)",
                    "basinc_valfi": r"(basınç|pressure|valve)",
                    "yon_kontrol_valfi": r"(4/2|4/3|3/2|valve)",
                    "tank_sembol": r"(tank|V=|LT)",
                    "cizgi_borular": r"(boru|pipe|hat)",
                    "yon_oklari": r"(yön|direction|ok)",
                    "bar_basinc": r"(\d{2,3}.*?bar)",
                    "debi_bilgi": r"(\d+.*?lt/dak|cc/rev)",
                    "guc_bilgi": r"(\d+.*?kW|rpm)",
                    "hydraulic_scheme": r"(HYDRAULIC|hidrolik)",
                    "data_sheet": r"(DATA.*?SHEET|sheet)"
                }
                
                general_pattern = general_patterns.get(criterion_name)
                if general_pattern:
                    general_matches = re.findall(general_pattern, text, re.IGNORECASE)
                    if general_matches:
                        content = f"Genel eşleşme: {general_matches[0]}"
                        found = True
                        score = weight // 2
                    else:
                        content = "Bulunamadı"
                        found = False
                        score = 0
                else:
                    content = "Bulunamadı"
                    found = False
                    score = 0
            
            results[criterion_name] = HidrolikAnalysisResult(
                criteria_name=criterion_name,
                found=found,
                content=content,
                score=score,
                max_score=weight,
                details={"pattern_used": pattern, "matches_found": len(matches) if matches else 0}
            )
        
        return results
    
    def extract_specific_values(self, text: str) -> Dict[str, Any]:
        values = {}
        
        value_patterns = {
            "proje_no": r"(?:5231|DO\s*Ğ\s*U\s*PRES|DOĞU\s*PRES)",
            "sistem_tipi": r"(?:press\s*feeding\s*system|feeding\s*system)",
            "tarih": r"(\d{2}\.\d{2}\.\d{4})",
            "coil_tech": r"(?:Coil\s*TECH|CoilTECH)",
            "hidrolik_unite": r"(?:HİDROLİK\s*ÜNİTE|HYDRAULIC\s*UNIT)",
            "hidrolik_acici": r"(?:HİDROLİK\s*AÇICI|HYDRAULIC\s*OPENER)",
            "dogrultma": r"(?:DOĞRULTMA|STRAIGHTENING)",
            "tank_hacmi": r"(?:V=\s*(\d+)|(\d+)\s*LT)",
            "motor_gucu": r"(?:(\d+)\s*kW|(\d+)\s*HP)",
            "devir": r"(?:(\d+)\s*rpm)",
            "debi": r"(?:(\d+).*?lt/dak|(\d+).*?cc/rev)",
            "basinc_g38": r"(?:G3/8|G\s*3/8)",
            "basinc_g12": r"(?:G1/2|G\s*1/2)",
            "basinc_g14": r"(?:G1/4|G\s*1/4)",
            "tambur": r"(?:TAMBUR|DRUM)",
            "rhso_silindir": r"(?:RHSÖ\s*63X45X200|RHSÖ.*?OEMB)",
            "pilotlama": r"(?:PILOTLAMA|PILOT)",
            "data_sheet": r"(?:DATA\s*SHEET|HYDRAULIC\s*MANIFOLD\s*PLAN)",
            "manifold_plan": r"(?:MANIFOLD\s*PLAN|KOLEKTÖR\s*PLAN)",
            "teknik_resim_uyari": r"(?:Teknik\s*Resim\s*Üzerinden\s*Ölçü\s*Almayın)"
        }
        
        for key, pattern in value_patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                if isinstance(matches[0], tuple):
                    values[key] = next(match for match in matches[0] if match)
                else:
                    values[key] = matches[0].strip()
            else:
                values[key] = "Bulunamadı"
        
        return values
    
    def calculate_scores(self, analysis_results: Dict[str, Dict[str, HidrolikAnalysisResult]]) -> Dict[str, Any]:
        category_scores = {}
        total_score = 0
        total_max_score = 100
        
        for category, results in analysis_results.items():
            category_max = self.criteria_weights[category]
            category_earned = sum(result.score for result in results.values())
            category_possible = sum(result.max_score for result in results.values())
            
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
        logger.info("Hidrolik devre şeması analizi başlatılıyor...")
        
        pdf_text = self.extract_text_from_pdf(pdf_path)
        if not pdf_text:
            return {"error": "PDF okunamadı"}
        
        hydraulic_valid, hydraulic_message = self.check_hydraulic_validity(pdf_text)
        
        extracted_values = self.extract_specific_values(pdf_text)
        
        analysis_results = {}
        for category in self.criteria_weights.keys():
            analysis_results[category] = self.analyze_criteria(pdf_text, category)
        
        scores = self.calculate_scores(analysis_results)
        
        recommendations = self.generate_recommendations(analysis_results, scores)
        
        report = {
            "analiz_tarihi": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dosya_bilgileri": {
                "pdf_path": pdf_path,
                "docx_path": docx_path
            },
            "hidrolik_gecerliligi": {
                "gecerli": hydraulic_valid,
                "mesaj": hydraulic_message
            },
            "cikarilan_degerler": extracted_values,
            "kategori_analizleri": analysis_results,
            "puanlama": scores,
            "oneriler": recommendations,
            "ozet": {
                "toplam_puan": scores["total_score"],
                "yuzde": scores["overall_percentage"],
                "durum": "GEÇERLİ" if scores["overall_percentage"] >= 70 else "YETERSİZ",
                "hidrolik_durumu": "GEÇERLİ" if hydraulic_valid else "GEÇERSİZ"
            }
        }
        
        return report
    
    def generate_recommendations(self, analysis_results: Dict, scores: Dict) -> List[str]:
        recommendations = []
        
        for category, results in analysis_results.items():
            category_score = scores["category_scores"][category]["percentage"]
            
            if category_score < 50:
                recommendations.append(f"❌ {category} bölümü yetersiz (%{category_score:.1f})")
                
                missing_criteria = [name for name, result in results.items() if not result.found]
                if missing_criteria:
                    recommendations.append(f"  Eksik kriterler: {', '.join(missing_criteria)}")
            
            elif category_score < 80:
                recommendations.append(f"⚠️ {category} bölümü geliştirilmeli (%{category_score:.1f})")
            
            else:
                recommendations.append(f"✅ {category} bölümü yeterli (%{category_score:.1f})")
        
        if scores["overall_percentage"] < 70:
            recommendations.append("\n🚨 GENEL ÖNERİLER:")
            recommendations.append("- Şema ISO 1219 standardına uyumlu hale getirilmelidir")
            recommendations.append("- Hidrolik semboller eksiksiz olmalıdır")
            recommendations.append("- Sistem bilgileri detaylandırılmalıdır")
            recommendations.append("- Basınç ve debi değerleri belirtilmelidir")
        
        return recommendations
    
    def save_report_to_excel(self, report: Dict, output_path: str):
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            ozet_data = {
                'Kriter': ['Toplam Puan', 'Yüzde', 'Durum', 'Hidrolik Durumu'],
                'Değer': [
                    report['ozet']['toplam_puan'],
                    f"%{report['ozet']['yuzde']}",
                    report['ozet']['durum'],
                    report['ozet']['hidrolik_durumu']
                ]
            }
            pd.DataFrame(ozet_data).to_excel(writer, sheet_name='Özet', index=False)
            
            values_data = []
            for key, value in report['cikarilan_degerler'].items():
                values_data.append({'Kriter': key, 'Değer': value})
            pd.DataFrame(values_data).to_excel(writer, sheet_name='Çıkarılan Değerler', index=False)
            
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
                
                sheet_name = category[:31]
                pd.DataFrame(category_data).to_excel(writer, sheet_name=sheet_name, index=False)
        
        logger.info(f"Rapor Excel dosyası kaydedildi: {output_path}")
    
    def save_report_to_json(self, report: Dict, output_path: str):
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
    analyzer = HidrolikDevreAnalyzer()
    
    pdf_path = "Doğu Pres - Hidrolik Şemalar.pdf"
    docx_path = "Hidrolik Devre Şeması_Kriterleri_Puanlama.docx"
    
    if not os.path.exists(pdf_path):
        print(f"❌ PDF dosyası bulunamadı: {pdf_path}")
        return
    
    print("🔍 Hidrolik Devre Şeması Analizi Başlatılıyor...")
    print("=" * 60)
    
    report = analyzer.generate_detailed_report(pdf_path, docx_path)
    
    if "error" in report:
        print(f"❌ Hata: {report['error']}")
        return
    
    print("\n📊 ANALİZ SONUÇLARI")
    print("=" * 60)
    
    print(f"📅 Analiz Tarihi: {report['analiz_tarihi']}")
    print(f"📋 Toplam Puan: {report['ozet']['toplam_puan']}/100")
    print(f"📈 Yüzde: %{report['ozet']['yuzde']}")
    print(f"🎯 Durum: {report['ozet']['durum']}")
    print(f"⚙️ Hidrolik Durumu: {report['ozet']['hidrolik_durumu']}")
    
    print(f"\n⚠️ Hidrolik Geçerlilik: {report['hidrolik_gecerliligi']['mesaj']}")
    
    print("\n📋 ÖNEMLİ ÇIKARILAN DEĞERLER")
    print("-" * 40)
    important_values = ['proje_no', 'sistem_tipi', 'tarih', 'hidrolik_unite', 
                       'tank_hacmi', 'motor_gucu', 'devir', 'debi', 'tambur']
    
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
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_path = f"Hidrolik_Devre_Analiz_Raporu_{timestamp}.xlsx"
    json_path = f"Hidrolik_Devre_Analiz_Raporu_{timestamp}.json"
    
    analyzer.save_report_to_excel(report, excel_path)
    analyzer.save_report_to_json(report, json_path)
    
    print(f"\n💾 Raporlar kaydedildi:")
    print(f"   📊 Excel: {excel_path}")
    print(f"   📄 JSON: {json_path}")

if __name__ == "__main__":
    main()