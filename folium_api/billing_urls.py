from django.urls import path
from . import billing_views

urlpatterns = [
    path("plans/", billing_views.BillingPlansListView.as_view(), name="billing-plans"),
    path("checkout/", billing_views.CreateCheckoutPreferenceView.as_view(), name="billing-checkout"),
    path("payment-status/", billing_views.VerifyPaymentStatusView.as_view(), name="billing-payment-status"),
    path("webhook/mercadopago/", billing_views.MercadoPagoWebhookView.as_view(), name="billing-mp-webhook"),
    path("webhook/mercadopago", billing_views.MercadoPagoWebhookView.as_view(), name="billing-mp-webhook-no-slash"),
]
