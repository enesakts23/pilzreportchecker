from flask import Flask, request, jsonify
import os
from werkzeug.utils import secure_filename
from lvd_report import GroundingContinuityReportAnalyzer
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configure upload settings
UPLOAD_FOLDER = 'temp_uploads_lvd'
ALLOWED_EXTENSIONS = {'pdf'}

# Create upload folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/lvd-report', methods=['POST'])
def analyze_lvd_report():
    """LVD (Topraklama Süreklilik) raporu analiz API endpoint'i"""
    try:
        # Check if a file was sent in the request
        if 'file' not in request.files:
            return jsonify({
                'error': 'No file provided',
                'message': 'Lütfen analiz edilmek üzere bir dosya sağlayın'
            }), 400

        file = request.files['file']

        # Check if a file was selected
        if file.filename == '':
            return jsonify({
                'error': 'No file selected',
                'message': 'Lütfen bir dosya seçin'
            }), 400

        # Check if the file is allowed
        if not allowed_file(file.filename):
            return jsonify({
                'error': 'Invalid file type',
                'message': 'Sadece PDF dosyaları kabul edilir'
            }), 400

        try:
            # Secure the filename and save the file
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            logger.info(f"LVD raporu analiz ediliyor: {filename}")

            # Initialize analyzer and analyze the LVD report
            analyzer = GroundingContinuityReportAnalyzer()
            report = analyzer.generate_detailed_report(filepath)

            # Clean up - remove the temporary file
            try:
                os.remove(filepath)
                logger.info(f"Geçici dosya temizlendi: {filename}")
            except Exception as e:
                logger.warning(f"Geçici dosya silinemedi {filepath}: {e}")

            # Check if analysis was successful
            if "error" in report:
                return jsonify({
                    'error': 'Analysis failed',
                    'message': report['error']
                }), 500

            # Return the analysis results
            return jsonify({
                'success': True,
                'report_type': 'LVD (Topraklama Süreklilik) Raporu',
                'analysis_date': report['analiz_tarihi'],
                'file_info': {
                    'filename': filename,
                    'file_type': report['dosya_bilgileri']['file_type'],
                    'detected_language': report['cikarilan_degerler'].get('language_name', 'Bilinmiyor')
                },
                'summary': {
                    'total_score': report['ozet']['toplam_puan'],
                    'percentage': round(report['ozet']['yuzde'], 1),
                    'status': report['ozet']['final_durum'],
                    'date_validity': report['ozet']['tarih_durumu'],
                    'pass_status': report['ozet']['gecme_durumu'],
                    'failure_reason': report['ozet'].get('fail_nedeni')
                },
                'date_validity': {
                    'is_valid': report['tarih_gecerliligi']['gecerli'],
                    'measurement_date': report['tarih_gecerliligi']['olcum_tarihi'],
                    'report_date': report['tarih_gecerliligi']['rapor_tarihi'],
                    'message': report['tarih_gecerliligi']['mesaj']
                },
                'extracted_values': report['cikarilan_degerler'],
                'category_scores': report['puanlama']['category_scores'],
                'recommendations': report['oneriler'],
                'detailed_analysis': report['kategori_analizleri']
            }), 200

        except Exception as e:
            # Clean up in case of error
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass

            logger.error(f"LVD raporu analiz hatası: {str(e)}")
            return jsonify({
                'error': 'Analysis failed',
                'message': f'Analiz sırasında hata oluştu: {str(e)}'
            }), 500

    except Exception as e:
        logger.error(f"Server hatası: {str(e)}")
        return jsonify({
            'error': 'Server error',
            'message': f'Sunucu hatası: {str(e)}'
        }), 500

@app.route('/api/lvd-health', methods=['GET'])
def health_check():
    """LVD API sağlık kontrolü"""
    return jsonify({
        'status': 'healthy',
        'service': 'LVD Report Analyzer API',
        'message': 'LVD rapor analiz servisi çalışıyor',
        'version': '1.0',
        'supported_formats': ['PDF'],
        'upload_folder': UPLOAD_FOLDER,
        'max_file_size': '16MB'
    }), 200

@app.route('/api/lvd-info', methods=['GET'])
def api_info():
    """LVD API bilgileri"""
    return jsonify({
        'api_name': 'LVD (Topraklama Süreklilik) Rapor Analiz API',
        'description': 'Topraklama süreklilik ölçüm raporlarını analiz eder ve uygunluk değerlendirmesi yapar',
        'endpoints': {
            'POST /api/lvd-report': {
                'description': 'LVD raporunu analiz eder',
                'parameters': {
                    'file': 'Analiz edilecek rapor dosyası (PDF)'
                },
                'response': 'Detaylı analiz raporu ve puanlama'
            },
            'GET /api/lvd-health': {
                'description': 'API sağlık durumu kontrolü',
                'response': 'Servis durumu bilgisi'
            },
            'GET /api/lvd-info': {
                'description': 'API bilgileri ve kullanım kılavuzu',
                'response': 'API dokümantasyonu'
            }
        },
        'analysis_criteria': {
            'Genel Rapor Bilgileri': {
                'weight': 15,
                'includes': ['Proje adı/numarası', 'Ölçüm tarihi', 'Rapor tarihi', 'Tesis/bölge/hat', 'Rapor numarası', 'Revizyon', 'Firma/personel']
            },
            'Ölçüm Metodu ve Standart Referansları': {
                'weight': 15,
                'includes': ['Ölçüm cihazı', 'Kalibrasyon', 'Standartlar (EN 60204-1)']
            },
            'Ölçüm Sonuç Tablosu': {
                'weight': 25,
                'includes': ['Sıra numarası', 'Makine/hat/bölge', 'Ölçüm noktası', 'RLO değeri', 'Yük iletken kesiti', 'Referans değeri', 'Uygunluk durumu']
            },
            'Uygunluk Değerlendirmesi': {
                'weight': 20,
                'includes': ['Toplam ölçüm nokta', 'Uygun nokta sayısı', 'Uygunsuz işaretleme', 'Standart referans uygunluk']
            },
            'Görsel ve Teknik Dökümantasyon': {
                'weight': 10,
                'includes': ['Cihaz bağlantı fotoğrafı', 'Görsel dokümantasyon']
            },
            'Sonuç ve Öneriler': {
                'weight': 15,
                'includes': ['Genel uygunluk', 'Standart atıf']
            }
        },
        'passing_criteria': {
            'minimum_score': 70,
            'date_validity': 'Ölçüm tarihi ile rapor tarihi arası maksimum 1 yıl',
            'critical_sections': ['Ölçüm Sonuç Tablosu', 'Uygunluk Değerlendirmesi']
        },
        'supported_languages': ['Türkçe', 'İngilizce', 'Almanca', 'Fransızca', 'İspanyolca', 'İtalyanca'],
        'features': [
            'PDF dosya desteği',
            'PyPDF2 ile metin çıkarma',
            'Offline çeviri desteği',
            'Otomatik dil tespiti',
            'Tarih geçerliliği kontrolü (kaldırıldı)',
            'Detaylı puanlama sistemi',
            'Kategori bazlı analiz',
            'Önerilerin sunulması',
            'Uygunsuz ölçümlerin tespiti'
        ]
    }), 200

@app.errorhandler(413)
def too_large(e):
    """Dosya boyutu çok büyük hatası"""
    return jsonify({
        'error': 'File too large',
        'message': 'Dosya boyutu 16MB limitini aşıyor'
    }), 413

@app.errorhandler(400)
def bad_request(e):
    """Kötü istek hatası"""
    return jsonify({
        'error': 'Bad request',
        'message': 'Geçersiz istek'
    }), 400

@app.errorhandler(500)
def internal_error(e):
    """İç sunucu hatası"""
    return jsonify({
        'error': 'Internal server error',
        'message': 'Sunucu hatası oluştu'
    }), 500

if __name__ == '__main__':
    # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    logger.info("LVD Rapor Analiz API başlatılıyor...")
    logger.info(f"Upload klasörü: {UPLOAD_FOLDER}")
    logger.info(f"Desteklenen formatlar: {', '.join(ALLOWED_EXTENSIONS)}")
    logger.info("API endpoint'leri:")
    logger.info("  POST /api/lvd-report - LVD raporu analizi")
    logger.info("  GET  /api/lvd-health  - Sağlık kontrolü")
    logger.info("  GET  /api/lvd-info    - API bilgileri")
    
    # Start the Flask server
    app.run(host='0.0.0.0', port=5007, debug=True) 
