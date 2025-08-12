from flask import Flask, request, jsonify
import os
from werkzeug.utils import secure_filename
import re
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

UPLOAD_FOLDER = 'temp_uploads'
ALLOWED_EXTENSIONS = {'pdf'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

@dataclass
class ComponentDetection:
    component_type: str
    label: str
    position: Tuple[int, int]
    confidence: float
    bounding_box: Tuple[int, int, int, int]
    
@dataclass
class CircuitAnalysisResult:
    criteria_name: str
    found: bool
    content: str
    score: float
    max_score: float
    details: Dict[str, Any]
    visual_evidence: List[ComponentDetection]

class AdvancedCircuitAnalyzer:
    def __init__(self):
        self.hydraulic_criteria_weights = {
            "Enerji Kaynağı": 25,
            "Hidrolik Semboller ve Bileşenler": 30,
            "Akış Yönü ve Bağlantı Hattı": 20,
            "Sistem Bilgileri ve Etiketler": 15,
            "Başlık ve Belgelendirme": 10
        }
        
        self.hydraulic_criteria_details = {
            "Enerji Kaynağı": {
                "basinc_yagi": {"pattern": r"(?i)(?:hidrolik|yağ|oil|basınç|pressure|fluid)", "weight": 8},
                "basinc_aralik": {"pattern": r"(?i)(?:\d{2,3}(?:\.\d+)?.*?(?:bar|Bar|BAR|MPa|psi))", "weight": 8},
                "sivil_guc": {"pattern": r"(?i)(?:sıvı|liquid|hydraulic|hidrolik|fluid|oil|yağ)", "weight": 5},
                "yuksek_basinc": {"pattern": r"(?i)(?:\d{2,3}(?:\.\d+)?.*?(?:bar|Bar|BAR|MPa|psi))", "weight": 4}
            },
            "Hidrolik Semboller ve Bileşenler": {
                "pompa_sembol": {"pattern": r"(?i)(?:pompa|pump|[0-9]+[PM][0-9]+|P\d+|M\d+)", "weight": 7},
                "motor_sembol": {"pattern": r"(?i)(?:motor|Motor|[0-9]+M[0-9]+|M\d+|drive)", "weight": 7},
                "silindir_sembol": {"pattern": r"(?i)(?:silindir|cylinder|piston|çift\s*etkili|tek\s*etkili|actuator)", "weight": 6},
                "basinc_valfi": {"pattern": r"(?i)(?:basınç|pressure|valve|valf|[0-9]+R[0-9]+|R\d+|relief)", "weight": 5},
                "yon_kontrol_valfi": {"pattern": r"(?i)(?:4/[23]|3/2|DCV|yön\s*kontrol|valve|valf|directional)", "weight": 5}
            },
            "Akış Yönü ve Bağlantı Hattı": {
                "cizgi_borular": {"pattern": r"(?i)(?:boru|pipe|hat|line|çizgi|hose|tube)", "weight": 6},
                "yon_oklari": {"pattern": r"(?i)(?:yön|direction|ok|arrow|akış|flow)", "weight": 6},
                "pompa_cikis": {"pattern": r"(?i)(?:pompa.*?(?:çıkış|çıkışı)|pump.*?output|basınç\s*hatt|pressure\s*line|discharge)", "weight": 4},
                "tank_donus": {"pattern": r"(?i)(?:tank.*?(?:dönüş|dönüşü)|return|tahliye|drain|suction)", "weight": 4}
            },
            "Sistem Bilgileri ve Etiketler": {
                "bar_basinc": {"pattern": r"(?i)(?:\d{2,3}(?:\.\d+)?.*?(?:bar|Bar|BAR|MPa|psi))", "weight": 4},
                "debi_bilgi": {"pattern": r"(?i)(?:\d+(?:\.\d+)?.*?(?:cc/rev|cc/dk|lt/dak|lt/min|l/min|gpm))", "weight": 4},
                "guc_bilgi": {"pattern": r"(?i)(?:\d+(?:\.\d+)?.*?(?:kW|HP|hp|güç|power)|(?:\d{3,4}.*?rpm))", "weight": 4},
                "tank_hacmi": {"pattern": r"(?i)(?:V\s*=\s*\d+|(?:\d+).*?(?:LT|lt|L|l)|tank.*?(?:hacmi|hacim|volume))", "weight": 3}
            },
            "Başlık ve Belgelendirme": {
                "hydraulic_scheme": {"pattern": r"(?i)(?:HYDRAULIC|hydraulic|HİDROLİK|hidrolik|hydro)", "weight": 3},
                "data_sheet": {"pattern": r"(?i)(?:DATA\s*SHEET|data.*?sheet|veri.*?sayfası|specification)", "weight": 3},
                "manifold_plan": {"pattern": r"(?i)(?:MANIFOLD\s*PLAN|manifold|kolektör|collector|block)", "weight": 2},
                "cizim_standardi": {"pattern": r"(?i)(?:ISO\s*1219|standart|standard|DIN|EN)", "weight": 2}
            }
        }
        
        self.component_templates = {
            "hydraulic": {
                "pump": ["P1", "P2", "P3", "PUMP", "POMPA"],
                "motor": ["M1", "M2", "M3", "MOTOR"],
                "valve": ["V1", "V2", "V3", "VALVE", "VALF"],
                "cylinder": ["C1", "C2", "C3", "CYL", "SİLİNDİR"],
                "tank": ["T1", "T2", "TANK", "TAMBUR"],
                "filter": ["F1", "F2", "FİLTRE", "FILTER"]
            }
        }

    def extract_text_from_pdf(self, pdf_path: str) -> str:
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
                return text
        except Exception as e:
            logger.error(f"PDF text extraction error: {e}")
            return ""

    def extract_images_from_pdf(self, pdf_path: str) -> List[Any]:
        logger.info("Image extraction is temporarily disabled")
        return []

    def perform_ocr_on_images(self, images: List[Any]) -> List[str]:
        logger.info("OCR functionality is temporarily disabled")
        return []

    def detect_components_in_images(self, images: List[Any], circuit_type: str) -> List[ComponentDetection]:
        logger.info("Component detection is temporarily disabled")
        return []

    def determine_circuit_type(self, text: str, images: List[Any]) -> Tuple[str, float]:
        return "hydraulic", 1.0

    def _is_relevant_component(self, component: ComponentDetection, criterion_name: str) -> bool:
        return False

    def analyze_criteria(self, text: str, images: List[Any], category: str, 
                        circuit_type: str) -> Dict[str, CircuitAnalysisResult]:
        results = {}
        criteria = self.hydraulic_criteria_details.get(category, {})
        
        combined_text = text
        if images:
            ocr_results = self.perform_ocr_on_images(images)
            combined_text += " " + " ".join(ocr_results)
        
        detected_components = self.detect_components_in_images(images, circuit_type)
        
        for criterion_name, criterion_data in criteria.items():
            pattern = criterion_data["pattern"]
            weight = criterion_data["weight"]
            
            text_matches = re.findall(pattern, combined_text, re.IGNORECASE | re.MULTILINE)
            
            relevant_components = [comp for comp in detected_components 
                                 if self._is_relevant_component(comp, criterion_name)]
            
            if text_matches or relevant_components:
                content_parts = []
                if text_matches:
                    content_parts.append(f"Text: {str(text_matches[:3])}")
                if relevant_components:
                    comp_labels = [comp.label for comp in relevant_components[:5]]
                    content_parts.append(f"Components: {comp_labels}")
                
                content = " | ".join(content_parts)
                found = True
                
                text_score = min(weight * 0.8, len(text_matches) * (weight * 0.2))
                component_score = min(weight * 0.2, len(relevant_components) * (weight * 0.1))
                score = text_score + component_score
                
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
                    "visual_matches": len(relevant_components)
                },
                visual_evidence=relevant_components
            )
        
        return results

    def extract_values(self, text: str) -> Dict[str, str]:
        values = {}
        
        pressure_matches = re.findall(r'(\d{2,3}(?:\.\d+)?)\s*(?:bar|Bar|BAR|MPa|psi)', text, re.IGNORECASE)
        if pressure_matches:
            values['pressure_values'] = ', '.join(pressure_matches[:3])
        
        flow_matches = re.findall(r'(\d+(?:\.\d+)?)\s*(?:cc/rev|cc/dk|lt/dak|lt/min|l/min|gpm)', text, re.IGNORECASE)
        if flow_matches:
            values['flow_values'] = ', '.join(flow_matches[:3])
        
        power_matches = re.findall(r'(\d+(?:\.\d+)?)\s*(?:kW|HP|hp)', text, re.IGNORECASE)
        if power_matches:
            values['power_values'] = ', '.join(power_matches[:3])
        
        volume_matches = re.findall(r'(?:V\s*=\s*)?(\d+)\s*(?:LT|lt|L|l)', text, re.IGNORECASE)
        if volume_matches:
            values['volume_values'] = ', '.join(volume_matches[:3])
        
        return values

    def calculate_scores(self, category_analyses: Dict[str, Dict[str, CircuitAnalysisResult]]) -> Dict[str, Any]:
        scoring = {
            "category_scores": {},
            "total_score": 0,
            "max_total_score": 100,
            "percentage": 0
        }
        
        for category, weight in self.hydraulic_criteria_weights.items():
            if category in category_analyses:
                category_score = sum(result.score for result in category_analyses[category].values())
                max_category_score = sum(result.max_score for result in category_analyses[category].values())
                
                normalized_score = min(category_score, weight)
                percentage = (normalized_score / weight * 100) if weight > 0 else 0
                
                scoring["category_scores"][category] = {
                    "raw_score": category_score,
                    "normalized": normalized_score,
                    "max_weight": weight,
                    "percentage": percentage
                }
                
                scoring["total_score"] += normalized_score
        
        scoring["percentage"] = (scoring["total_score"] / scoring["max_total_score"]) * 100
        return scoring

    def generate_recommendations(self, category_analyses: Dict[str, Dict[str, CircuitAnalysisResult]], 
                               scoring: Dict[str, Any]) -> List[str]:
        recommendations = []
        
        if scoring["percentage"] < 70:
            recommendations.append("⚠️ Hidrolik devre şeması minimum gereklilikleri sağlamamaktadır.")
        
        for category, results in category_analyses.items():
            missing_count = sum(1 for result in results.values() if not result.found)
            if missing_count > 0:
                recommendations.append(f"🔧 {category} kategorisinde {missing_count} eksik kriter bulunmaktadır.")
        
        if scoring["percentage"] >= 90:
            recommendations.append("✅ Mükemmel! Hidrolik devre şeması tüm kriterleri karşılamaktadır.")
        elif scoring["percentage"] >= 70:
            recommendations.append("✅ İyi! Hidrolik devre şeması genel gereklilikleri sağlamaktadır.")
        else:
            recommendations.append("❌ Hidrolik devre şeması yeniden gözden geçirilmelidir.")
        
        return recommendations

    def analyze_circuit_diagram(self, pdf_path: str) -> Dict[str, Any]:
        try:
            logger.info(f"Starting analysis of: {pdf_path}")
            
            text = self.extract_text_from_pdf(pdf_path)
            if not text:
                return {"error": "PDF'den metin çıkarılamadı"}
            
            images = self.extract_images_from_pdf(pdf_path)
            circuit_type, confidence = self.determine_circuit_type(text, images)
            
            category_analyses = {}
            for category in self.hydraulic_criteria_weights.keys():
                category_analyses[category] = self.analyze_criteria(text, images, category, circuit_type)
            
            extracted_values = self.extract_values(text)
            scoring = self.calculate_scores(category_analyses)
            recommendations = self.generate_recommendations(category_analyses, scoring)
            
            status = "GEÇERLİ" if scoring["percentage"] >= 70 else "GEÇERSİZ"
            
            report = {
                "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "file_info": {
                    "filename": os.path.basename(pdf_path),
                    "text_length": len(text),
                    "images_count": len(images)
                },
                "circuit_type": {
                    "detected_type": circuit_type,
                    "confidence": confidence
                },
                "extracted_values": extracted_values,
                "category_analyses": {
                    category: {name: asdict(result) for name, result in results.items()}
                    for category, results in category_analyses.items()
                },
                "scoring": scoring,
                "recommendations": recommendations,
                "summary": {
                    "total_score": scoring["total_score"],
                    "percentage": round(scoring["percentage"], 1),
                    "status": status,
                    "circuit_type": "Hidrolik Devre"
                }
            }
            
            logger.info(f"Analysis completed. Score: {scoring['percentage']:.1f}%")
            return report
            
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return {"error": f"Analiz hatası: {str(e)}"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/report', methods=['POST'])
def analyze_circuit():
    try:
        if 'file' not in request.files:
            return jsonify({
                'error': 'No file provided',
                'message': 'Lütfen isteğe bir PDF dosyası ekleyin'
            }), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({
                'error': 'No file selected',
                'message': 'Lütfen yüklenecek bir dosya seçin'
            }), 400

        if not allowed_file(file.filename):
            return jsonify({
                'error': 'Invalid file type',
                'message': 'Sadece PDF dosyaları kabul edilir'
            }), 400

        try:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            analyzer = AdvancedCircuitAnalyzer()
            full_report = analyzer.analyze_circuit_diagram(filepath)

            try:
                os.remove(filepath)
            except Exception as e:
                logger.warning(f"Geçici dosya silinemedi {filepath}: {e}")

            # Sadece özet bilgileri döndür
            simplified_report = {
                "analiz_tarihi": full_report["analysis_date"],
                "dosya_adi": os.path.basename(filepath),
                "devre_tipi": full_report["circuit_type"],
                "onemli_bilgiler": full_report["extracted_values"],
                "puanlama": {
                    "toplam_puan": full_report["summary"]["total_score"],
                    "yuzde": full_report["summary"]["percentage"],
                    "durum": full_report["summary"]["status"],
                    "devre_tipi": full_report["summary"]["circuit_type"]
                },
                "kategori_puanlari": {
                    kategori: {
                        "puan": score_data["normalized"],
                        "max_puan": score_data["max_weight"],
                        "yuzde": round(score_data["percentage"], 1)
                    }
                    for kategori, score_data in full_report["scoring"]["category_scores"].items()
                },
                "oneriler": full_report["recommendations"][:5]  # Sadece ilk 5 öneri
            }

            return jsonify({
                'success': True,
                'report': simplified_report
            }), 200

        except Exception as e:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass

            logger.error(f"Devre analiz hatası: {str(e)}")
            return jsonify({
                'error': 'Analysis failed',
                'message': str(e)
            }), 500

    except Exception as e:
        logger.error(f"Sunucu hatası: {str(e)}")
        return jsonify({
            'error': 'Server error',
            'message': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'Hidrolik devre analiz servisi çalışıyor',
        'port': 5003,
        'service': 'Hydraulic Circuit Analysis API'
    }), 200

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    print("🚀 Hidrolik Devre Analiz API'si başlatılıyor...")
    print("📍 Port: 5003")
    print("🔗 Endpoints:")
    print("   POST /api/report - PDF analizi")
    print("   GET /api/health - Sağlık kontrolü")
    print("📋 Test için Postman kullanın:")
    print("   URL: http://localhost:5003/api/report")
    print("   Method: POST")
    print("   Body: form-data, Key: file, Type: File")
    
    app.run(host='0.0.0.0', port=5003, debug=True)
