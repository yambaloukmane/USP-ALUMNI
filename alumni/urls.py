from django.urls import path

from .views import admin_area, auth, dues, messaging, network, profile, public

urlpatterns = [
    # Pages publiques et application installable
    path("", public.home, name="home"),
    path("about/", public.about, name="about"),
    path("services/", public.services, name="services"),
    path("contact/", public.contact, name="contact"),
    path("treasury/", public.treasury, name="treasury"),
    path("offline/", public.offline, name="offline"),
    path("manifest.webmanifest", public.manifest, name="manifest"),
    path("sw.js", public.service_worker, name="service_worker"),

    # Compte
    path("login/", auth.login_view, name="login"),
    path("logout/", auth.logout_view, name="logout"),
    path("register/", auth.register, name="register"),
    path("register/verify/", auth.register_verify, name="register_verify"),
    path("register/resend/", auth.register_resend, name="register_resend"),
    path("forgot/", auth.forgot, name="forgot"),
    path("forgot/verify/", auth.forgot_verify, name="forgot_verify"),
    path("profile/", profile.profile, name="profile"),
    path("profile/avatar/", profile.profile_avatar, name="profile_avatar"),
    path("avatar/<str:member_id>/", profile.avatar_image, name="avatar"),

    # Réseau
    path("feed/", network.feed, name="feed"),
    path("jobs/propose/", network.job_propose, name="job_propose"),
    path("members/", network.members, name="members"),
    path("events/", network.events_page, name="events"),
    path("events/<str:event_id>/rsvp/", network.event_rsvp, name="event_rsvp"),
    path("gallery/", network.gallery_page, name="gallery"),
    path("gallery/upload/", network.gallery_upload, name="gallery_upload"),
    path("gallery/<str:photo_id>/delete/", network.gallery_delete, name="gallery_delete"),

    # Cotisations
    path("cotisations/", dues.dues_page, name="dues"),
    path("cotisations/payer/<str:due_id>/", dues.dues_pay, name="dues_pay"),
    path("cotisations/retour/", dues.dues_return, name="dues_return"),
    path("cotisations/notification/", dues.dues_notify, name="dues_notify"),

    # Messagerie
    path("messages/", messaging.messages_page, name="messages"),
    path("messages/api/contacts/", messaging.api_contacts, name="api_contacts"),
    path("messages/api/conversation/", messaging.api_conversation, name="api_conversation"),
    path("messages/api/send/", messaging.api_send, name="api_send"),
    path("messages/api/voice/", messaging.api_voice, name="api_voice"),
    path("messages/api/unread/", messaging.api_unread, name="api_unread"),

    # Espace Responsable
    path("responsable/", admin_area.responsable, name="responsable"),
    path("responsable/logout/", admin_area.responsable_logout, name="responsable_logout"),
    path("responsable/members/<str:member_id>/delete/", admin_area.member_delete, name="admin_member_delete"),
    path("responsable/members/<str:member_id>/role/", admin_area.member_role, name="admin_member_role"),
    path("responsable/members/<str:member_id>/status/", admin_area.member_status, name="admin_member_status"),
    path("responsable/news/add/", admin_area.news_add, name="admin_news_add"),
    path("responsable/news/<str:news_id>/edit/", admin_area.news_edit, name="admin_news_edit"),
    path("responsable/news/<str:news_id>/delete/", admin_area.news_delete, name="admin_news_delete"),
    path("responsable/jobs/add/", admin_area.job_add, name="admin_job_add"),
    path("responsable/jobs/<str:job_id>/edit/", admin_area.job_edit, name="admin_job_edit"),
    path("responsable/jobs/<str:job_id>/approve/", admin_area.job_approve, name="admin_job_approve"),
    path("responsable/jobs/<str:job_id>/delete/", admin_area.job_delete, name="admin_job_delete"),
    path("responsable/events/add/", admin_area.event_add, name="admin_event_add"),
    path("responsable/events/<str:event_id>/delete/", admin_area.event_delete, name="admin_event_delete"),
    path("responsable/dues/generate/", admin_area.dues_generate, name="admin_dues_generate"),
    path("responsable/dues/<str:due_id>/toggle/", admin_area.dues_toggle, name="admin_dues_toggle"),
    path("responsable/members/print/", admin_area.members_print, name="admin_members_print"),
    path("responsable/export/members.csv", admin_area.export_members, name="admin_export_members"),
    path("responsable/export/dues.csv", admin_area.export_dues, name="admin_export_dues"),
]
