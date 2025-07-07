import re
import os
import json
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional
import PyPDF2
from docx import Document
import pandas as pd
from dataclasses import dataclass, asdict
import logging
import math
from collections import Counter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ComponentDetection:
    """Detected component information"""
    component_type: str
    label: str
    position: Tuple[int, int]
    confidence: float
    bounding_box: Tuple[int, int, int, int]
    
@dataclass
class CircuitAnalysisResult:
    """Analysis result for each criterion"""
    criteria_name: str
    found: bool
    content: str
    score: float
    max_score: float
    details: Dict[str, Any]
    visual_evidence: List[ComponentDetection]

class PneumaticCircuitAnalyzer:
    """Advanced pneumatic circuit diagram analyzer"""
    
    def __init__(self):
        # Pneumatic circuit criteria weights
        self.pneumatic_criteria_weights = {
            "Enerji Kaynağı": 25,
            "Pnömatik Semboller ve Bileşenler": 30,
            "Akış Yönü ve Bağlantı Hattı": 20,
            "Sistem Bilgileri ve Etiketler": 15,
            "Başlık ve Belgelendirme": 10
        }
        
        # Pneumatic circuit component patterns
        self.pneumatic_criteria_details = {
            "Enerji Kaynağı": {
                "hava_kaynagi": {"pattern": r"(?i)(?:◉|hava|air|basınçlı\s*hava|compressed\s*air|supply|P(?:\s*=\s*\d+(?:\.\d+)?(?:\s*bar|Bar|BAR|MPa|psi))?)", "weight": 8},
                "basinc_aralik": {"pattern": r"(?i)(?:\d{1,2}(?:\.\d+)?.*?(?:bar|Bar|BAR|MPa|psi)|P\s*=\s*\d+(?:\.\d+)?(?:\s*bar|Bar|BAR|MPa|psi))", "weight": 8},
                "hava_hazırlama": {"pattern": r"(?i)(?:⬭|filtre|filter|regülatör|regulator|yağlayıcı|lubricator|FRL|⬭---|FR[L]?|F/R|F/R/L)", "weight": 5},
                "basinc_gosterge": {"pattern": r"(?i)(?:manometre|pressure\s*gauge|gösterge|indicator|P[I]?|PI|PT)", "weight": 4}
            },
            "Pnömatik Semboller ve Bileşenler": {
                "silindir_sembol": {"pattern": r"(?i)(?:⇳|⇵|silindir|cylinder|piston|çift\s*etkili|tek\s*etkili|actuator|double\s*acting|single\s*acting)", "weight": 7},
                "valf_sembol": {"pattern": r"(?i)(?:▭⟶▭|▭⟶▭⟶▭|▭⟶▭⟶▭⟶▭|▭⟶▭⟶▭⟶▭⟶▭|valf|valve|[2-5][/][2-5]|[0-9]+[V][0-9]+|V\d+|solenoid)", "weight": 7},
                "yon_kontrol": {"pattern": r"(?i)(?:5/[23]|4/[23]|3/2|2/2|yön\s*kontrol|directional|control|way\s*valve)", "weight": 6},
                "basinc_kontrol": {"pattern": r"(?i)(?:basınç|pressure|regulator|relief|emniyet|PR|PRV|safety)", "weight": 5},
                "hiz_kontrol": {"pattern": r"(?i)(?:⇨⇦|hız|speed|flow\s*control|akış\s*kontrol|FC|FCV)", "weight": 5}
            },
            "Akış Yönü ve Bağlantı Hattı": {
                "hava_hatti": {"pattern": r"(?i)(?:▬|hava|air|hat|line|boru|pipe|hose|supply\s*line)", "weight": 6},
                "yon_oklari": {"pattern": r"(?i)(?:→|←|↑|↓|⇒|⇐|⇑|⇓|yön|direction|ok|arrow|akış|flow)", "weight": 6},
                "giris_cikis": {"pattern": r"(?i)(?:A|B|P|R|S|giriş|çıkış|input|output|port|bağlantı|connection)", "weight": 4},
                "egzoz_hatti": {"pattern": r"(?i)(?:⊥|egzoz|exhaust|tahliye|drain|vent|R|S|EA|EB)", "weight": 4}
            },
            "Sistem Bilgileri ve Etiketler": {
                "calisma_basinci": {"pattern": r"(?i)(?:P\s*=\s*\d{1,2}(?:\.\d+)?.*?(?:bar|Bar|BAR|MPa|psi)|\d{1,2}(?:\.\d+)?.*?(?:bar|Bar|BAR|MPa|psi))", "weight": 4},
                "hava_tuketimi": {"pattern": r"(?i)(?:Q\s*=\s*\d+(?:\.\d+)?.*?(?:l/min|lt/dak|cfm|m³/h)|\d+(?:\.\d+)?.*?(?:l/min|lt/dak|cfm|m³/h))", "weight": 4},
                "strok_bilgi": {"pattern": r"(?i)(?:s\s*=\s*\d+(?:\.\d+)?.*?(?:mm|cm|m)|strok|stroke|\d+(?:\.\d+)?.*?(?:mm|cm|m))", "weight": 4},
                "valf_tipi": {"pattern": r"(?i)(?:normalde.*?(?:açık|kapalı)|NC|NO|normally|N[CO]|spring\s*return|yay\s*geri\s*dönüşlü)", "weight": 3}
            },
            "Başlık ve Belgelendirme": {
                "pneumatic_scheme": {"pattern": r"(?i)(?:PNEUMATIC|pneumatic|PNÖMATİK|pnömatik|pneumatik|ŞEMA|şema|scheme|diagram)", "weight": 3},
                "data_sheet": {"pattern": r"(?i)(?:DATA\s*SHEET|data.*?sheet|veri.*?sayfası|specification|teknik\s*bilgi)", "weight": 3},
                "manifold_plan": {"pattern": r"(?i)(?:MANIFOLD\s*PLAN|manifold|kolektör|collector|block|dağıtıcı)", "weight": 2},
                "cizim_standardi": {"pattern": r"(?i)(?:ISO\s*1219|DIN\s*ISO\s*1219|standart|standard|DIN|EN)", "weight": 2}
            }
        }
        
        # Component detection templates
        self.component_templates = {
            "pneumatic": {
                "cylinder": ["⇳", "⇵", "C1", "C2", "C3", "CYL", "SİLİNDİR", "CYLINDER", "PISTON"],
                "valve": ["▭⟶▭", "▭⟶▭⟶▭", "▭⟶▭⟶▭⟶▭", "▭⟶▭⟶▭⟶▭⟶▭", "V1", "V2", "V3", "VALVE", "VALF", "2/2", "3/2", "4/2", "5/2"],
                "frl": ["⬭", "⬭---", "F1", "F2", "FRL", "FİLTRE", "FILTER", "REGULATOR", "REGÜLATÖR"],
                "sensor": ["◉", "S1", "S2", "SENSOR", "SENSÖR", "PI", "PT", "PS"],
                "regulator": ["⬭---", "R1", "R2", "REG", "REGÜLATÖR", "PR", "PRV"],
                "silencer": ["⊥", "M1", "M2", "SUSTURUCU", "MUFFLER", "EXHAUST"],
                "flow_control": ["⇨⇦", "FC1", "FC2", "FLOW", "AKIŞ", "FCV"],
                "timer": ["⧗", "T1", "T2", "TIMER", "ZAMANLAYICI"],
                "pressure_switch": ["PS1", "PS2", "PRESSURE", "BASINÇ", "SWITCH"],
                "direction_arrows": ["→", "←", "↑", "↓", "⇒", "⇐", "⇑", "⇓"]
            }
        }

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF using PyPDF2"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    page_text = re.sub(r'\s+', ' ', page_text)
                    page_text = page_text.replace('|', ' ')
                    text += page_text + "\n"
                
                # Text normalization
                text = text.replace('—', '-')
                text = text.replace('"', '"').replace('"', '"')
                text = text.replace('´', "'")
                text = re.sub(r'[^\x00-\x7F\u00C0-\u00FF\u0100-\u017F\u0180-\u024F]+', ' ', text)
                text = text.strip()
                return text
        except Exception as e:
            logger.error(f"PDF text extraction error: {e}")
            return ""

    def analyze_criteria(self, text: str, category: str) -> Dict[str, CircuitAnalysisResult]:
        """Analyze criteria for pneumatic circuit diagrams"""
        results = {}
        criteria = self.pneumatic_criteria_details.get(category, {})
        
        # Combine text and OCR results
        combined_text = text
        
        for criterion_name, criterion_data in criteria.items():
            pattern = criterion_data["pattern"]
            weight = criterion_data["weight"]
            
            # Text-based matching
            text_matches = re.findall(pattern, combined_text, re.IGNORECASE | re.MULTILINE)
            
            # Scoring logic with partial credit
            if text_matches:
                content = f"Text: {str(text_matches[:3])}"
                found = True
                
                # Calculate score with partial credit
                score = min(weight * 0.8, len(text_matches) * (weight * 0.2))
                score = min(score, weight)
            else:
                content = "Not found"
                found = False
                score = 0
            
            results[criterion_name] = CircuitAnalysisResult(
                criteria_name=criterion_name,
                found=found,
                content=content,
                score=score,
                max_score=weight,
                details={
                    "pattern_used": pattern,
                    "text_matches": len(text_matches) if text_matches else 0,
                    "visual_matches": 0
                },
                visual_evidence=[]
            )
        
        return results

    def calculate_scores(self, analysis_results: Dict[str, Dict[str, CircuitAnalysisResult]]) -> Dict[str, Any]:
        """Calculate final scores with partial credit and curve"""
        category_scores = {}
        total_score = 0
        total_max_score = 100

        for category, results in analysis_results.items():
            category_max = self.pneumatic_criteria_weights[category]
            category_earned = sum(result.score for result in results.values())
            category_possible = sum(result.max_score for result in results.values())

            # Apply scoring curve for partial credit
            if category_possible > 0:
                raw_percentage = category_earned / category_possible
                adjusted_percentage = math.pow(raw_percentage, 0.7)  # Less aggressive curve
                normalized_score = adjusted_percentage * category_max
            else:
                normalized_score = 0

            category_scores[category] = {
                "earned": category_earned,
                "possible": category_possible,
                "normalized": round(normalized_score, 2),
                "max_weight": category_max,
                "percentage": round((category_earned / category_possible * 100), 2) if category_possible > 0 else 0
            }

            total_score += normalized_score

        # Apply final adjustment (10% boost)
        final_score = min(100, total_score * 1.1)

        return {
            "category_scores": category_scores,
            "total_score": round(final_score, 2),
            "total_max_score": total_max_score,
            "overall_percentage": round((final_score / total_max_score * 100), 2)
        }

    def extract_specific_values(self, text: str) -> Dict[str, Any]:
        """Extract specific values from pneumatic circuit text"""
        values = {
            "proje_no": "Not found",
            "sistem_tipi": "Not found",
            "tarih": "Not found",
            "calisma_basinci": "Not found",
            "hava_tuketimi": "Not found",
            "strok": "Not found",
            "valf_tipi": "Not found",
            "kontrol_tipi": "Not found"
        }
        
        # Project number pattern
        project_match = re.search(r"(?:5231|DO\s*Ğ\s*U\s*PRES|DOĞU\s*PRES)", text)
        if project_match:
            values["proje_no"] = project_match.group()
        
        # System type pattern
        system_match = re.search(r"(?:press\s*feeding\s*system|feeding\s*system)", text)
        if system_match:
            values["sistem_tipi"] = system_match.group()
        
        # Date pattern
        date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
        if date_match:
            values["tarih"] = date_match.group(1)
        
        # Working pressure pattern
        pressure_match = re.search(r"(?:(\d{1,2}(?:\.\d+)?)\s*(?:bar|Bar|BAR))", text)
        if pressure_match:
            values["calisma_basinci"] = pressure_match.group(1)
        
        # Air consumption pattern
        consumption_match = re.search(r"(?:(\d+(?:\.\d+)?)\s*(?:l/min|lt/dak|cfm))", text)
        if consumption_match:
            values["hava_tuketimi"] = consumption_match.group(1)
        
        # Stroke pattern
        stroke_match = re.search(r"(?:(\d+(?:\.\d+)?)\s*(?:mm|cm))", text)
        if stroke_match:
            values["strok"] = stroke_match.group(1)
        
        # Valve type pattern
        valve_match = re.search(r"(?:normalde\s*(açık|kapalı)|N[CO])", text)
        if valve_match:
            values["valf_tipi"] = valve_match.group(1) or valve_match.group()
        
        # Control type pattern
        control_match = re.search(r"(?:(elektrik|pneumatic|manual)\s*kontrol)", text)
        if control_match:
            values["kontrol_tipi"] = control_match.group(1)
        
        return values

    def generate_recommendations(self, analysis_results: Dict, scores: Dict) -> List[str]:
        """Generate recommendations based on analysis results"""
        recommendations = []
        
        # Check pneumatic validity
        valid_criteria_count = sum(1 for category, results in analysis_results.items() 
                                 for result in results.values() if result.found)
        total_criteria_count = sum(len(results) for results in analysis_results.values())
        pneumatic_validity = valid_criteria_count / total_criteria_count
        
        recommendations.append(f"⚠️ Pnömatik Geçerlilik: Pnömatik devre güvenilirlik: %{pneumatic_validity*100:.1f} ({valid_criteria_count}/{total_criteria_count} kriter)")

        for category, results in analysis_results.items():
            category_score = scores["category_scores"][category]["percentage"]
            
            if category_score < 40:
                recommendations.append(f"❌ {category} bölümü yetersiz (%{category_score:.1f})")
                missing_criteria = [name for name, result in results.items() if not result.found]
                if missing_criteria:
                    recommendations.append(f"  Eksik kriterler: {', '.join(missing_criteria)}")
            elif category_score < 70:
                recommendations.append(f"⚠️ {category} bölümü geliştirilmeli (%{category_score:.1f})")
            else:
                recommendations.append(f"✅ {category} bölümü yeterli (%{category_score:.1f})")

        if scores["overall_percentage"] < 70:
            recommendations.append("\n🚨 GENEL ÖNERİLER:")
            recommendations.extend([
                "- Şema ISO 1219 standardına uyumlu hale getirilmelidir",
                "- Pnömatik semboller eksiksiz olmalıdır",
                "- Sistem bilgileri detaylandırılmalıdır",
                "- Basınç ve hava tüketimi değerleri belirtilmelidir"
            ])

        return recommendations

    def analyze_circuit_diagram(self, pdf_path: str) -> Dict[str, Any]:
        """Main analysis function for pneumatic circuit diagrams"""
        logger.info("Starting pneumatic circuit diagram analysis...")

        # Extract text
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            return {"error": "Could not read PDF"}

        # Analyze based on criteria
        analysis_results = {}
        criteria_weights = self.pneumatic_criteria_weights

        for category in criteria_weights.keys():
            analysis_results[category] = self.analyze_criteria(text, category)

        # Calculate scores
        scores = self.calculate_scores(analysis_results)
        
        # Extract specific values
        extracted_values = self.extract_specific_values(text)
        
        # Generate recommendations
        recommendations = self.generate_recommendations(analysis_results, scores)

        # Prepare report
        report = {
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_info": {
                "pdf_path": pdf_path
            },
            "circuit_type": {
                "type": "pneumatic",
                "confidence": 100.0
            },
            "extracted_values": extracted_values,
            "category_analyses": analysis_results,
            "scoring": scores,
            "recommendations": recommendations,
            "summary": {
                "total_score": scores["total_score"],
                "percentage": scores["overall_percentage"],
                "status": "PASS" if scores["overall_percentage"] >= 70 else "FAIL",
                "circuit_type": "PNEUMATIC"
            }
        }

        return report

    def save_report_to_excel(self, report: Dict, output_path: str):
        """Save analysis report to Excel file"""
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Summary sheet
            summary_data = {
                'Criterion': ['Total Score', 'Percentage', 'Status', 'Circuit Type'],
                'Value': [
                    report['summary']['total_score'],
                    f"%{report['summary']['percentage']}",
                    report['summary']['status'],
                    report['summary']['circuit_type']
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)

            # Extracted values sheet
            values_data = []
            for key, value in report['extracted_values'].items():
                values_data.append({'Criterion': key, 'Value': value})
            pd.DataFrame(values_data).to_excel(writer, sheet_name='Extracted_Values', index=False)

            # Category analysis sheets
            for category, results in report['category_analyses'].items():
                category_data = []
                for criterion, result in results.items():
                    category_data.append({
                        'Criterion': criterion,
                        'Found': result.found,
                        'Content': result.content,
                        'Score': result.score,
                        'Max Score': result.max_score,
                        'Visual Matches': len(result.visual_evidence)
                    })
                # Clean sheet name - replace invalid characters
                sheet_name = category.replace('/', '_').replace('\\', '_')[:31]  # Excel sheet name length limit
                pd.DataFrame(category_data).to_excel(writer, sheet_name=sheet_name, index=False)

        logger.info(f"Report saved to Excel: {output_path}")

    def save_report_to_json(self, report: Dict, output_path: str):
        """Save analysis report to JSON file"""
        json_report = {}
        for key, value in report.items():
            if key == 'category_analyses':
                json_report[key] = {}
                for category, results in value.items():
                    json_report[key][category] = {}
                    for criterion, result in results.items():
                        json_report[key][category][criterion] = asdict(result)
            else:
                json_report[key] = value

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_report, f, ensure_ascii=False, indent=2)

        logger.info(f"Report saved to JSON: {output_path}")

def main():
    """Main function"""
    analyzer = PneumaticCircuitAnalyzer()
    
    pdf_path = "Doğu Pres - Pnömatik Şemalar.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"❌ PDF file not found: {pdf_path}")
        return
    
    print("🔍 Pnömatik Devre Şeması Analizi Başlatılıyor...")
    print("=" * 60)
    
    report = analyzer.analyze_circuit_diagram(pdf_path)
    
    if "error" in report:
        print(f"❌ Error: {report['error']}")
        return
    
    print("\n📊 ANALİZ SONUÇLARI")
    print("=" * 60)
    
    print(f"📅 Analiz Tarihi: {report['analysis_date']}")
    print(f"📋 Toplam Puan: {report['summary']['total_score']}/100")
    print(f"📈 Yüzde: %{report['summary']['percentage']}")
    print(f"🎯 Durum: {report['summary']['status']}")
    print(f"⚙️ Pnömatik Durumu: {report['summary']['circuit_type']}")
    
    print("\n📋 ÖNEMLİ ÇIKARILAN DEĞERLER")
    print("-" * 40)
    for key, value in report['extracted_values'].items():
        print(f"{key.replace('_', ' ').title()}: {value}")
    
    print("\n📊 KATEGORİ PUANLARI")
    print("-" * 40)
    for category, score_data in report['scoring']['category_scores'].items():
        print(f"{category}: {score_data['normalized']}/{score_data['max_weight']} (%{score_data['percentage']:.1f})")
    
    print("\n💡 ÖNERİLER")
    print("-" * 40)
    for recommendation in report['recommendations']:
        print(recommendation)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_path = f"Pnömatik_Devre_Analiz_Raporu_{timestamp}.xlsx"
    json_path = f"Pnömatik_Devre_Analiz_Raporu_{timestamp}.json"
    
    analyzer.save_report_to_excel(report, excel_path)
    analyzer.save_report_to_json(report, json_path)
    
    print(f"\n💾 Raporlar kaydedildi:")
    print(f"   📊 Excel: {excel_path}")
    print(f"   📄 JSON: {json_path}")
    
    # Genel değerlendirme bölümü
    print("\n📋 GENEL DEĞERLENDİRME")
    print("=" * 60)
    percentage = report['summary']['percentage']
    if percentage >= 70:
        print("✅ SONUÇ: GEÇERLİ")
        print(f"🌟 Toplam Başarı: %{percentage:.1f}")
        print("📝 Değerlendirme: Pnömatik devre şeması genel olarak yeterli kriterleri sağlamaktadır.")
    else:
        print("❌ SONUÇ: GEÇERSİZ")
        print(f"⚠️ Toplam Başarı: %{percentage:.1f}")
        print("📝 Değerlendirme: Pnömatik devre şeması minimum gereklilikleri sağlamamaktadır.")
        print("\n⚠️ EKSİK GEREKLİLİKLER:")
        
        # Her kategori için eksik gereklilikleri listele
        for category, results in report['category_analyses'].items():
            missing_items = []
            for criterion, result in results.items():
                if not result.found:
                    missing_items.append(criterion)
            
            if missing_items:
                print(f"\n🔍 {category}:")
                for item in missing_items:
                    # Eksik kriter adlarını daha anlaşılır hale getir
                    readable_name = {
                        "hava_kaynagi": "Hava Kaynağı",
                        "basinc_aralik": "Basınç Aralığı",
                        "hava_hazırlama": "Hava Hazırlama Ünitesi",
                        "basinc_gosterge": "Basınç Göstergesi",
                        "silindir_sembol": "Silindir Sembolü",
                        "valf_sembol": "Valf Sembolü",
                        "yon_kontrol": "Yön Kontrol Valfi",
                        "basinc_kontrol": "Basınç Kontrol Valfi",
                        "hiz_kontrol": "Hız Kontrol Valfi",
                        "hava_hatti": "Hava Hattı",
                        "yon_oklari": "Yön Okları",
                        "giris_cikis": "Giriş/Çıkış Portları",
                        "egzoz_hatti": "Egzoz Hattı",
                        "calisma_basinci": "Çalışma Basıncı",
                        "hava_tuketimi": "Hava Tüketimi",
                        "strok_bilgi": "Strok Bilgisi",
                        "valf_tipi": "Valf Tipi",
                        "pneumatic_scheme": "Pnömatik Şema",
                        "data_sheet": "Veri Sayfası",
                        "manifold_plan": "Manifold Planı",
                        "cizim_standardi": "Çizim Standardı"
                    }.get(item, item)
                    print(f"   ❌ {readable_name}")
        
        print("\n📌 YAPILMASI GEREKENLER:")
        print("1. Eksik sembolleri ekleyin")
        print("2. Basınç ve hava tüketimi değerlerini belirtin")
        print("3. Akış yönlerini ve bağlantıları gösterin")
        print("4. ISO 1219 standardına uygun hale getirin")
        print("5. Sistem bilgilerini detaylandırın")

if __name__ == "__main__":
    main()
