#!/usr/bin/env python3
"""
Test script to verify image extraction improvements for CDN URLs
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from bs4 import BeautifulSoup
from onyx.connectors.web.connector import extract_images_from_html

def test_image_extraction():
    """Test image extraction with CDN URLs"""
    
    # Test HTML with the CDN image from Seclore adoption site
    test_html = '''
    <html>
    <body>
        <img alt="image" loading="lazy" width="624" height="376.52244897959184" 
             decoding="async" data-nimg="1" style="color:transparent;height:auto" 
             sizes="(max-width: 546px) 100vw, 93vw" 
             srcset="https://images.spr.so/cdn-cgi/imagedelivery/j42No7y-dcokJuNgXeA0ig/04e3575c-b3f0-48c9-a8e6-60f9a3461608/2/w=640,quality=90,fit=scale-down 640w, https://images.spr.so/cdn-cgi/imagedelivery/j42No7y-dcokJuNgXeA0ig/04e3575c-b3f0-48c9-a8e6-60f9a3461608/2/w=750,quality=90,fit=scale-down 750w, https://images.spr.so/cdn-cgi/imagedelivery/j42No7y-dcokJuNgXeA0ig/04e3575c-b3f0-48c9-a8e6-60f9a3461608/2/w=828,quality=90,fit=scale-down 828w, https://images.spr.so/cdn-cgi/imagedelivery/j42No7y-dcokJuNgXeA0ig/04e3575c-b3f0-48c9-a8e6-60f9a3461608/2/w=1080,quality=90,fit=scale-down 1080w, https://images.spr.so/cdn-cgi/imagedelivery/j42No7y-dcokJuNgXeA0ig/04e3575c-b3f0-48c9-a8e6-60f9a3461608/2/w=1200,quality=90,fit=scale-down 1200w, https://images.spr.so/cdn-cgi/imagedelivery/j42No7y-dcokJuNgXeA0ig/04e3575c-b3f0-48c9-a8e6-60f9a3461608/2/w=1920,quality=90,fit=scale-down 1920w, https://images.spr.so/cdn-cgi/imagedelivery/j42No7y-dcokJuNgXeA0ig/04e3575c-b3f0-48c9-a8e6-60f9a3461608/2/w=2048,quality=90,fit=scale-down 2048w, https://images.spr.so/cdn-cgi/imagedelivery/j42No7y-dcokJuNgXeA0ig/04e3575c-b3f0-48c9-a8e6-60f9a3461608/2/w=3840,quality=90,fit=scale-down 3840w" 
             src="https://images.spr.so/cdn-cgi/imagedelivery/j42No7y-dcokJuNgXeA0ig/04e3575c-b3f0-48c9-a8e6-60f9a3461608/2/w=3840,quality=90,fit=scale-down">
        
        <!-- Test traditional image -->
        <img src="https://example.com/image.jpg" alt="traditional image">
        
        <!-- Test CDN image without extension -->
        <img src="https://cdn.example.com/images/photo" alt="cdn image">
    </body>
    </html>
    '''
    
    soup = BeautifulSoup(test_html, 'html.parser')
    base_url = "https://adoption.seclore.com"
    
    print("Testing image extraction improvements...")
    print("=" * 50)
    
    images = extract_images_from_html(soup, base_url)
    
    print(f"Found {len(images)} images:")
    for i, img in enumerate(images, 1):
        reason = img.get('extraction_reason', 'unknown')
        print(f"  {i}. URL: {img['url']}")
        print(f"     Alt: {img.get('alt', 'N/A')}")
        print(f"     Reason: {reason}")
        print()
    
    # Check if the CDN image was extracted
    cdn_images = [img for img in images if 'images.spr.so' in img['url']]
    if cdn_images:
        print("✅ SUCCESS: CDN images were extracted!")
        print(f"   Found {len(cdn_images)} CDN images")
    else:
        print("❌ FAILURE: No CDN images were extracted")
    
    return len(images) > 0

if __name__ == "__main__":
    success = test_image_extraction()
    if success:
        print("\n✅ Image extraction test passed!")
    else:
        print("\n❌ Image extraction test failed!")
        sys.exit(1) 