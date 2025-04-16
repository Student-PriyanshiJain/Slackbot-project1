from django.urls import path
from . views import slack_events
from bot import views

urlpatterns = [
    path("/slack/events" ,views.slack_events, name="slack_events"),
]


