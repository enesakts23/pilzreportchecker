from flask import Flask, request, jsonify
import os
from werkzeug.utils import secure_filename
from loto_report_checker import LOTOReportAnalyzer
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configure upload settings
UPLOAD_FOLDER = 'temp_uploads_loto'
ALLOWED_EXTENSIONS = {'pdf'}

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_analysis_response(report):
    """Format the analysis response like loto_report_checker.py output"""
    lines = []
    
    # Header
    lines.append("🔒 LOTO Rapor Analizi Sonuçları")
    lines.append("=" * 60)
    
    # Basic info
    lines.append(f"📅 Analiz Tarihi: {report['analiz_tarihi']}")
    lang = report['dosya_bilgisi']['detected_language'].upper()
    lines.append(f"🔍 Tespit Edilen Dil: {lang}")
    
    # Document type info
    doc_type = report['dosya_bilgisi'].get('document_type', 'analysis_report')
    if doc_type == 'procedure_document':
        lines.append(f"📋 Belge Türü: Prosedür Dökümanı")
        lines.append(f"🎯 Eşik Değer: %{report['dosya_bilgisi']['pass_threshold']}")
    else:
        lines.append(f"📋 Belge Türü: Analiz Raporu")
        lines.append(f"🎯 Eşik Değer: %{report['dosya_bilgisi']['pass_threshold']}")
    
    lines.append(f"📋 Toplam Puan: {report['ozet']['toplam_puan']}/100")
    lines.append(f"📈 Yüzde: %{report['ozet']['yuzde']}")
    lines.append(f"🎯 Durum: {report['ozet']['durum']}")
    lines.append(f"📄 Rapor Tipi: {report['ozet']['rapor_tipi']}")
    lines.append("")
    
    # Date validity
    lines.append("📅 TARİH GEÇERLİLİĞİ")
    lines.append("-" * 40)
    date_info = report['tarih_gecerliligi']
    lines.append(f"Rapor Tarihi: {date_info['report_date']}")
    lines.append(f"Yaş: {date_info['days_old']} gün")
    lines.append(f"Geçerlilik: {date_info['validity_reason']}")
    lines.append("")
    
    # Important extracted values
    lines.append("📋 ÖNEMLİ ÇIKARILAN DEĞERLER")
    lines.append("-" * 40)
    
    extracted_values = report.get('cikarilan_degerler', {})
    value_mappings = {
        'proje_adi': 'Proje Adı',
        'rapor_tarihi': 'Rapor Tarihi',
        'hazirlayan_firma': 'Hazırlayan Firma',
        'kabul_durumu': 'Kabul Durumu'
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
    
    doc_type = report['dosya_bilgisi'].get('document_type', 'analysis_report')
    pass_threshold = report['dosya_bilgisi'].get('pass_threshold', 70)
    
    if report['ozet']['yuzde'] >= pass_threshold:
        lines.append("✅ SONUÇ: GEÇERLİ")
        lines.append(f"🌟 Toplam Başarı: %{report['ozet']['yuzde']:.1f}")
        if doc_type == 'procedure_document':
            lines.append("📝 Değerlendirme: LOTO prosedürü genel olarak yeterli kriterleri sağlamaktadır.")
        else:
            lines.append("📝 Değerlendirme: LOTO raporu genel olarak yeterli kriterleri sağlamaktadır.")
    else:
        lines.append("❌ SONUÇ: GEÇERSİZ/EKSİK")
        lines.append(f"⚠️ Toplam Başarı: %{report['ozet']['yuzde']:.1f}")
        if doc_type == 'procedure_document':
            lines.append("📝 Değerlendirme: LOTO prosedürü minimum gereklilikleri sağlamamaktadır.")
        else:
            lines.append("📝 Değerlendirme: LOTO raporu minimum gereklilikleri sağlamamaktadır.")
        
        # Show missing requirements if failed
        lines.append("\n⚠️ EKSİK GEREKLİLİKLER:")
        if 'kategori_analizleri' in report:
            for category, results in report['kategori_analizleri'].items():
                missing_items = []
                for criterion, result in results.items():
                    if isinstance(result, dict):
                        found = result.get('found', False)
                    else:
                        found = getattr(result, 'found', False)
                    
                    if not found:
                        missing_items.append(criterion)
                
                if missing_items:
                    lines.append(f"\n🔍 {category}:")
                    for item in missing_items:
                        readable_name = item.replace('_', ' ').title()
                        lines.append(f"   ❌ {readable_name}")
    
    return "\n".join(lines)

@app.route('/api/loto-report', methods=['POST'])
def analyze_loto_report():
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

            # Initialize analyzer and analyze the LOTO report
            analyzer = LOTOReportAnalyzer()
            
            report = analyzer.analyze_loto_report(filepath)

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

            # Format the response like loto_report_checker.py output
            response_text = format_analysis_response(report)
            
            return jsonify({
                'success': True,
                'analysis_text': response_text,
                'detailed_data': {
                    'analiz_tarihi': report.get('analiz_tarihi'),
                    'dosya_bilgisi': report.get('dosya_bilgisi'),
                    'tarih_gecerliligi': report.get('tarih_gecerliligi'),
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

            logger.error(f"Error analyzing LOTO report: {str(e)}")
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

@app.route('/api/loto-health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'message': 'LOTO Report Analysis Service is running',
        'service': 'LOTO Report Analyzer'
    }), 200

@app.route('/api/loto-info', methods=['GET'])
def service_info():
    return jsonify({
        'service': 'LOTO Report Analysis API',
        'version': '1.0.0',
        'description': 'API for analyzing LOTO (Lockout Tagout) reports and procedures',
        'endpoints': {
            '/api/loto-report': 'POST - Upload and analyze LOTO report/procedure PDF',
            '/api/loto-health': 'GET - Health check',
            '/api/loto-info': 'GET - Service information'
        },
        'supported_formats': ['PDF'],
        'max_file_size': '16MB',
        'supported_languages': ['Turkish', 'English'],
        'document_types': [
            'Analysis Report (70% threshold)',
            'Procedure Document (50% threshold)'
        ],
        'scoring_categories': [
            'Genel Rapor Bilgileri (10 points)',
            'Tesis ve Makine Tanımı (10 points)',
            'LOTO Politikası Değerlendirmesi (10 points)',
            'Enerji Kaynakları Analizi (25 points)',
            'İzolasyon Noktaları ve Prosedürler (25 points)',
            'Teknik Değerlendirme ve Sonuçlar (15 points)',
            'Dokümantasyon ve Referanslar (5 points)'
        ],
        'total_points': 100,
        'features': [
            'Automatic document type detection',
            'English to Turkish term translation',
            'Adaptive scoring based on document type',
            'Comprehensive pattern matching',
            'Multi-language support'
        ]
    }), 200

@app.route('/', methods=['GET'])
def root():
    return jsonify({
        'message': 'LOTO Report Analysis API Server',
        'version': '1.0.0',
        'status': 'running',
        'port': 5006,
        'endpoints': {
            '/api/loto-report': 'POST - Upload and analyze LOTO report/procedure PDF',
            '/api/loto-health': 'GET - Health check',
            '/api/loto-info': 'GET - Service information'
        }
    }), 200

if __name__ == '__main__':
    # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    logger.info("Starting LOTO Report Analysis Server on port 5006...")
    logger.info("Available endpoints:")
    logger.info("  POST /api/loto-report - Upload and analyze LOTO PDF")
    logger.info("  GET  /api/loto-health - Health check")
    logger.info("  GET  /api/loto-info - Service information")
    logger.info("  GET  / - Root endpoint")
    
    app.run(debug=True, host='0.0.0.0', port=5006)
