from django.views import View
from django.http import HttpResponse
from django.shortcuts import render

# Create your views here.

# Usen clases para declarar las views. Un ejemplo hecho con la IA:

'''
class ContactView(View):

    # Handles HTTP GET requests (e.g., loading the page)

    def get(self, request):
        return HttpResponse("This is the contact page (GET request).")

    # Handles HTTP POST requests (e.g., submitting a form)

    def post(self, request):
        name = request.POST.get('name', 'Guest')
        return HttpResponse(f"Thank you for your submission, {name}! (POST request).")
'''