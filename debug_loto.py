#!/usr/bin/env python3
"""
LOTO rapor analizi debug script'i
İngilizce belgenin içeriğini ve pattern eşleşmelerini detaylı analiz eder
"""

import re
import os
import PyPDF2
from loto_report_checker import LOTOReportAnalyzer

def extract_text_simple(pdf_path):
    """Basit PDF metin çıkarma"""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                text += page_text + "\n"
            return text
    except Exception as e:
        print(f"PDF okuma hatası: {e}")
        return ""

def debug_patterns(text, analyzer):
    """Pattern'ları debug et"""
    print("🔍 PATTERN DEBUG ANALİZİ")
    print("=" * 80)
    
    # Metin örnekleri göster
    print(f"\n📝 METİN ÖRNEKLERI (İlk 1000 karakter):")
    print("-" * 50)
    print(text[:1000])
    print("-" * 50)
    
    print(f"\n📝 METİN ÖRNEKLERI (Son 1000 karakter):")
    print("-" * 50)
    print(text[-1000:])
    print("-" * 50)
    
    for category, criteria in analyzer.criteria_details.items():
        print(f"\n🔍 {category}")
        print("=" * 60)
        
        for criterion_name, criterion_data in criteria.items():
            pattern = criterion_data["pattern"]
            print(f"\n🎯 {criterion_name}")
            print(f"Pattern: {pattern}")
            
            # Pattern eşleşmelerini bul
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            
            if matches:
                print(f"✅ Bulunan eşleşmeler ({len(matches)} adet):")
                for i, match in enumerate(matches[:5]):  # İlk 5 eşleşmeyi göster
                    print(f"   {i+1}. {match}")
                if len(matches) > 5:
                    print(f"   ... ve {len(matches)-5} eşleşme daha")
            else:
                print("❌ Eşleşme bulunamadı")
                
                # Benzer terimleri ara
                if "Energy" in pattern:
                    similar_matches = re.findall(r'\b\w*[Ee]nergy\w*\b', text, re.IGNORECASE)
                    if similar_matches:
                        print(f"   🔍 Metinde bulunan benzer terimler: {set(similar_matches)}")
                
                if "Lock" in pattern or "lock" in pattern:
                    similar_matches = re.findall(r'\b\w*[Ll]ock\w*\b', text, re.IGNORECASE)
                    if similar_matches:
                        print(f"   🔍 Metinde bulunan benzer terimler: {set(similar_matches)}")
                        
                if "Isolation" in pattern:
                    similar_matches = re.findall(r'\b\w*[Ii]solat\w*\b', text, re.IGNORECASE)
                    if similar_matches:
                        print(f"   🔍 Metinde bulunan benzer terimler: {set(similar_matches)}")
                        
                if "Machine" in pattern:
                    similar_matches = re.findall(r'\b\w*[Mm]achine\w*\b', text, re.IGNORECASE)
                    if similar_matches:
                        print(f"   🔍 Metinde bulunan benzer terimler: {set(similar_matches)}")

def main():
    """Ana debug fonksiyonu"""
    
    # İngilizce belgeyi analiz et
    english_pdf = "24-410-Loto-Procedure-V01.pdf"
    
    if not os.path.exists(english_pdf):
        print(f"❌ PDF dosyası bulunamadı: {english_pdf}")
        return
    
    print(f"🔍 DEBUG ANALİZİ: {english_pdf}")
    print("=" * 80)
    
    # Metni çıkar
    text = extract_text_simple(english_pdf)
    
    if not text:
        print("❌ PDF'den metin çıkarılamadı")
        return
    
    print(f"📊 Metin uzunluğu: {len(text)} karakter")
    print(f"📊 Satır sayısı: {len(text.splitlines())}")
    
    # Analyzer oluştur
    analyzer = LOTOReportAnalyzer()
    
    # Dil tespiti
    detected_lang = analyzer.detect_language(text)
    print(f"🌐 Tespit edilen dil: {detected_lang.upper()}")
    
    # Çeviri varsa uygula
    if detected_lang == 'en':
        print("🔄 İngilizce terim çevirisi uygulanıyor...")
        translated_text = analyzer.translate_to_turkish(text, detected_lang)
        print(f"📊 Çeviri sonrası metin uzunluğu: {len(translated_text)} karakter")
        
        # Çeviri örnekleri göster
        print("\n🔄 ÇEVİRİ ÖRNEKLERİ:")
        print("-" * 40)
        sample_lines = translated_text.splitlines()[:20]
        for line in sample_lines:
            if line.strip():
                print(f"  {line.strip()}")
                break
        
        text = translated_text
    
    # Pattern'ları debug et
    debug_patterns(text, analyzer)
    
    print("\n" + "=" * 80)
    print("DEBUG ANALİZİ TAMAMLANDI")
    
if __name__ == "__main__":
    main()
