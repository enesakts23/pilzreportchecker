from flask import Flask, request, jsonify
import os
from werkzeug.utils import secure_filename
from manuel_report_checker import ManualReportAnalyzer
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configure upload settings
UPLOAD_FOLDER = 'temp_uploads_manuel'
ALLOWED_EXTENSIONS = {'pdf'}

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_analysis_response(report):
    """Format the analysis response like manuel_report_checker.py output"""
    lines = []
    
    # Header
    lines.append("📊 ANALİZ SONUÇLARI")
    lines.append("=" * 60)
    
    # Basic info
    lines.append(f"📅 Analiz Tarihi: {report['analiz_tarihi']}")
    lang = report['dosya_bilgisi']['detected_language'].upper()
    lines.append(f"🔍 Tespit Edilen Dil: {lang}")
    lines.append(f"📋 Toplam Puan: {report['ozet']['toplam_puan']}/100")
    lines.append(f"📈 Yüzde: %{report['ozet']['yuzde']}")
    lines.append(f"🎯 Durum: {report['ozet']['durum']}")
    lines.append(f"📄 Rapor Tipi: {report['ozet']['rapor_tipi']}")
    lines.append("")
    
    # Important extracted values
    lines.append("📋 ÖNEMLİ ÇIKARILAN DEĞERLER")
    lines.append("-" * 40)
    
    extracted_values = report.get('cikarilan_degerler', {})
    value_mappings = {
        'kilavuz_adi': 'Kılavuz Adı',
        'urun_modeli': 'Ürün Modeli',
        'hazırlama_tarihi': 'Hazırlama Tarihi',
        'hazirlayan': 'Hazırlayan'
    }
    
    for key, display_name in value_mappings.items():
        value = extracted_values.get(key, 'Bulunamadı')
        lines.append(f"{display_name}: {value}")
    lines.append("")
    
    # Category scores and details
    lines.append("📊 KATEGORİ PUANLARI VE DETAYLAR")
    lines.append("=" * 60)
    
    if 'puanlama' in report and 'category_scores' in report['puanlama']:
        for category, score_data in report['puanlama']['category_scores'].items():
            percentage = score_data['percentage']
            lines.append(f"\n🔍 {category}: {score_data['normalized']}/{score_data['max_weight']} (%{percentage:.1f})")
            lines.append("-" * 50)
            
            # Category analysis details
            if category in report.get('kategori_analizleri', {}):
                category_analysis = report['kategori_analizleri'][category]
                for criterion_name, criterion_result in category_analysis.items():
                    criterion_display = criterion_name.replace('_', ' ').title()
                    # Check if criterion_result is a dict or object
                    if isinstance(criterion_result, dict):
                        found = criterion_result.get('found', False)
                        score = criterion_result.get('score', 0)
                        max_score = criterion_result.get('max_score', 0)
                    else:
                        found = getattr(criterion_result, 'found', False)
                        score = getattr(criterion_result, 'score', 0)
                        max_score = getattr(criterion_result, 'max_score', 0)
                    
                    if found:
                        lines.append(f"  ✅ {criterion_display}: {score}/{max_score} puan")
                    else:
                        lines.append(f"  ❌ {criterion_display}: 0/{max_score} puan - BULUNAMADI")
    
    lines.append("\n" + "=" * 60)
    lines.append("")
    
    # Recommendations
    lines.append("💡 ÖNERİLER VE DEĞERLENDİRME")
    lines.append("-" * 40)
    
    if 'oneriler' in report:
        for recommendation in report['oneriler']:
            lines.append(recommendation)
    lines.append("")
    
    # Final evaluation
    lines.append("📋 GENEL DEĞERLENDİRME")
    lines.append("=" * 60)
    
    if report['ozet']['yuzde'] >= 70:
        lines.append("✅ SONUÇ: GEÇERLİ")
        lines.append(f"🌟 Toplam Başarı: %{report['ozet']['yuzde']:.1f}")
        lines.append("📝 Değerlendirme: Kullanma kılavuzu genel olarak yeterli kriterleri sağlamaktadır.")
    else:
        lines.append("❌ SONUÇ: YETERSİZ")
        lines.append(f"🌟 Toplam Başarı: %{report['ozet']['yuzde']:.1f}")
        lines.append("📝 Değerlendirme: Kullanma kılavuzu yetersiz kriterlere sahiptir ve iyileştirme gerektirir.")
    
    return "\n".join(lines)

@app.route('/api/manuel-report', methods=['POST'])
def analyze_manuel_report():
    try:
        # Check if a file was sent in the request
        if 'file' not in request.files:
            return jsonify({
                'error': 'No file provided',
                'message': 'Please provide a PDF file in the request'
            }), 400

        file = request.files['file']

        # Check if a file was selected
        if file.filename == '':
            return jsonify({
                'error': 'No file selected',
                'message': 'Please select a file to upload'
            }), 400

        # Check if the file is allowed
        if not allowed_file(file.filename):
            return jsonify({
                'error': 'Invalid file type',
                'message': 'Only PDF files are allowed'
            }), 400

        try:
            # Secure the filename and save the file
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Initialize analyzer and analyze the manual report
            analyzer = ManualReportAnalyzer()
            
            report = analyzer.analyze_manual_report(filepath)

            # Clean up - remove the temporary file
            try:
                os.remove(filepath)
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {filepath}: {e}")

            # Check if there was an error in the analysis
            if "error" in report:
                return jsonify({
                    'error': 'Analysis failed',
                    'message': report['error']
                }), 500

            # Format the response like manuel_report_checker.py output
            response_text = format_analysis_response(report)
            
            return jsonify({
                'success': True,
                'analysis_text': response_text,
                'detailed_data': {
                    'analiz_tarihi': report.get('analiz_tarihi'),
                    'dosya_bilgisi': report.get('dosya_bilgisi'),
                    'cikarilan_degerler': report.get('cikarilan_degerler'),
                    'kategori_analizleri': report.get('kategori_analizleri'),
                    'puanlama': report.get('puanlama'),
                    'oneriler': report.get('oneriler'),
                    'ozet': report.get('ozet')
                }
            }), 200

        except Exception as e:
            # Clean up in case of error
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass

            logger.error(f"Error analyzing manual report: {str(e)}")
            return jsonify({
                'error': 'Analysis failed',
                'message': str(e)
            }), 500

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({
            'error': 'Server error',
            'message': str(e)
        }), 500

@app.route('/api/manuel-health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'Manual Report Analysis Service is running',
        'service': 'Manual Report Analyzer'
    }), 200

@app.route('/api/manuel-info', methods=['GET'])
def service_info():
    return jsonify({
        'service': 'Manual Report Analysis API',
        'version': '1.0.0',
        'description': 'API for analyzing User Manual (Kullanma Kılavuzu) reports',
        'endpoints': {
            '/api/manuel-report': 'POST - Upload and analyze Manual report PDF',
            '/api/manuel-health': 'GET - Health check',
            '/api/manuel-info': 'GET - Service information'
        },
        'supported_formats': ['PDF'],
        'max_file_size': '16MB',
        'scoring_categories': [
            'Genel Bilgiler (10 points)',
            'Giriş ve Amaç (5 points)',
            'Güvenlik Bilgileri (15 points)',
            'Ürün Tanıtımı (10 points)',
            'Kurulum ve Montaj Bilgileri (15 points)',
            'Kullanım Talimatları (20 points)',
            'Bakım ve Temizlik (10 points)',
            'Arıza Giderme (15 points)'
        ],
        'total_points': 100,
        'pass_threshold': '70%'
    }), 200

if __name__ == '__main__':
    # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    logger.info("Starting Manual Report Analysis Server on port 5005...")
    app.run(debug=True, host='0.0.0.0', port=5005)
