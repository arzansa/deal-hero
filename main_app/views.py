from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import SignUpForm
from django.http import HttpResponse
from pprint import pprint
from .models import Product, Retailer, Wishlist, PriceHistory
import urllib.parse
import requests
import re
import os




def about(request):
    return render(request, 'about.html')

class Home(LoginView):
    template_name = 'home.html'

class Login(LoginView):
    template_name = 'login.html'
    
def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created successfully!')
            return redirect('login')  
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = SignUpForm()
    return render(request, 'signup.html', {'form': form})

def fetch_product_data(payload):
    response = requests.request(
        'POST',
        'https://realtime.oxylabs.io/v1/queries',
        auth=(os.environ.get('OXYLABS_USERNAME'), os.environ.get('OXYLABS_PASSWORD')),
        json=payload,
    )
    return response.json()

def get_logo_url(merchant_name):
    if '.' in merchant_name:
        cleaned_name = re.split(r'\.com|\.net|\.org', merchant_name)[0] + ".com"
        return f"https://img.logo.dev/{cleaned_name}?token=pk_MHqHMYHhSPqsrHGnE0dW1Q"
    
    cleaned_name = merchant_name.replace("'", "")
    cleaned_name = cleaned_name.replace(" ", "")
    
    return f"https://img.logo.dev/{cleaned_name}.com?token=pk_MHqHMYHhSPqsrHGnE0dW1Q"

def extract_url(full_url):
    parsed_url = urllib.parse.urlparse(full_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    return query_params.get('url', [full_url])[0]


def product_search(request):
    if request.method == 'POST':
        query = request.POST.get('query')

        amazon_payload = {
            'source': 'amazon_search',
            'domain_name': 'usa',
            'query': query,
            'start_page': 1,
            'pages': 1,
            'parse': True,
            'context': [
                {'key': 'category_id', 'value': 16391693031}
            ],
        }

        google_payload = {
            'source': 'google_shopping_search',
            'domain': 'com',
            'query': query,
            'pages': 1,
            'parse': True,
            'context': [
                {'key': 'min_price', 'value': 1},  
            ]
        }

        amz_data = fetch_product_data(amazon_payload)
        ggl_data = fetch_product_data(google_payload)

        
        
                                                     
        amz_results = amz_data['results'][0]['content']['results']['organic']
        ggl_results = ggl_data['results'][0]['content']['results']['organic']

        for product in amz_results:
            product['logo_url'] = get_logo_url('Amazon.com')
        
        for product in ggl_results:
            merchant_name = product['merchant']['name']
            product['logo_url'] = get_logo_url(merchant_name)

        valid_amz_products = [
            product for product in amz_results if product.get('price', 0) > 0
        ]
        
        valid_ggl_products = [
            product for product in ggl_results if product.get('price', 0) > 0
        ]

        if not valid_ggl_products and not valid_amz_products:
            return HttpResponse("Your search didn't produce any results.")

        def sorting_key(product):
            return (
                    -product.get('pos', 0),  
                    1 if product.get('is_amazons_choice', False) else 0,  
                    1 if product.get('best_seller', False) else 0,  
                    product.get('reviews_count', 0),  
                    product.get('rating', 0),  
                    -product['price'],  
            )

        amz_sorted_products = sorted(valid_amz_products, key=sorting_key, reverse=True)
        amz_best_product = amz_sorted_products[0]

        ggl_sorted_products = sorted(valid_ggl_products, key=sorting_key, reverse=True)
        ggl_best_product = ggl_sorted_products[0] if ggl_sorted_products else None

        return render(request, 'products/products_index.html', {
            'amz_best_product': amz_best_product,
            'amz_products': amz_sorted_products,
            'gg_best_product': ggl_best_product,
            'ggl_products': ggl_sorted_products,
        })

    return redirect('home')

@login_required
def fetch_product_details(request, product_id):
    if request.method == 'POST':
        payload = {
            'source': 'amazon_product',
            'domain': 'com',
            'query': f'{product_id}',
            'parse': True,
        }
        response = requests.request(
            'POST',
            'https://realtime.oxylabs.io/v1/queries',
            auth=(os.environ.get('OXYLABS_USERNAME'), os.environ.get('OXYLABS_PASSWORD')),
            json=payload,
        )
        data = response.json()
        
        product_name = data['results'][0]['content']['product_name']        
        category = data['results'][0]['content']['category'][0]['ladder'][-1]['name']        
        product_url = data['results'][0]['content']['url']        
        image_url = data['results'][0]['content']['images'][0]        
        description = data['results'][0]['content']['description']        
        rating = data['results'][0]['content']['rating']        
        in_stock = data['results'][0]['content']['stock'].lower() == 'in stock.'        
        price = data['results'][0]['content']['price']        
        retailer_name = data['results'][0]['content']['featured_merchant']['name']               
        retailer, created = Retailer.objects.get_or_create(name=retailer_name)      
        product, created = Product.objects.get_or_create(
            name=product_name,
            defaults={
                'category': category,
                'product_url': product_url,
                'image_url': image_url,
                'description': description,
                'rating': rating,
                'in_stock': in_stock,
                'price_drop_threshold': price,
                'user': request.user,
                'retailer': retailer
            }
        )
        PriceHistory.objects.create(
            product=product,
            price=price
        )
       
        Wishlist.objects.get_or_create(
            product_id=product,
            user=request.user
        )

        return HttpResponse(f"Product details fetched and saved successfully for {product_id}.")
    
    return redirect('home')