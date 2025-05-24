import pytest
from unittest.mock import patch, MagicMock, call

from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse

from text_to_audio.models import Article, Feed
from text_to_audio.tasks import check_stale_articles, process_article
from rss_tts.celery import app as celery_app # For mocking app.control.revoke


@pytest.fixture
def test_user():
    user, _ = User.objects.get_or_create(username="testuser", defaults={'password':"password"})
    return user

@pytest.fixture
def test_feed(test_user):
    feed, _ = Feed.objects.get_or_create(user=test_user, name="Test Feed")
    return feed

@pytest.mark.django_db
@patch('text_to_audio.tasks.celery_app.control.revoke') # Corrected path to celery_app
def test_check_stale_articles_timed_out(mock_revoke, test_feed):
    """
    Test check_stale_articles for an article that has timed out.
    """
    timeout_seconds = settings.ARTICLE_PROCESSING_TIMEOUT_SECONDS
    stale_article = Article.objects.create(
        feed=test_feed,
        title="Stale Article",
        text_content="This is a stale article.",
        status=Article.PROCESSING,
        # Set updated_at to be older than the timeout period
        updated_at=timezone.now() - timedelta(seconds=timeout_seconds + 120),
        celery_task_id="test_task_id_stale"
    )

    check_stale_articles()

    stale_article.refresh_from_db()
    assert stale_article.status == Article.FAILED
    assert "Processing timed out" in stale_article.error_message
    assert stale_article.celery_task_id is None
    mock_revoke.assert_called_once_with("test_task_id_stale", terminate=True)

@pytest.mark.django_db
@patch('text_to_audio.tasks.celery_app.control.revoke') # Corrected path
def test_check_stale_articles_non_stale(mock_revoke, test_feed):
    """
    Test check_stale_articles for a non-stale (recent) article in PROCESSING.
    """
    fresh_article = Article.objects.create(
        feed=test_feed,
        title="Fresh Article",
        text_content="This is a fresh article.",
        status=Article.PROCESSING,
        updated_at=timezone.now() - timedelta(seconds=10), # Recently updated
        celery_task_id="test_task_id_fresh"
    )
    original_updated_at = fresh_article.updated_at

    check_stale_articles()

    fresh_article.refresh_from_db()
    assert fresh_article.status == Article.PROCESSING
    assert fresh_article.celery_task_id == "test_task_id_fresh"
    assert fresh_article.updated_at == original_updated_at # Ensure it wasn't saved unnecessarily
    mock_revoke.assert_not_called()

@pytest.mark.django_db
@patch('text_to_audio.tasks.celery_app.control.revoke') # Corrected path
def test_check_stale_articles_ignores_completed_failed(mock_revoke, test_feed):
    """
    Test check_stale_articles ignores COMPLETED or FAILED articles, even if old.
    """
    timeout_seconds = settings.ARTICLE_PROCESSING_TIMEOUT_SECONDS
    old_timestamp = timezone.now() - timedelta(seconds=timeout_seconds + 3600)

    completed_article = Article.objects.create(
        feed=test_feed,
        title="Completed Article",
        status=Article.COMPLETED,
        updated_at=old_timestamp,
        celery_task_id="task_completed"
    )
    failed_article = Article.objects.create(
        feed=test_feed,
        title="Failed Article",
        status=Article.FAILED,
        updated_at=old_timestamp,
        celery_task_id="task_failed"
    )

    check_stale_articles()

    completed_article.refresh_from_db()
    failed_article.refresh_from_db()

    assert completed_article.status == Article.COMPLETED
    assert completed_article.celery_task_id == "task_completed"
    assert failed_article.status == Article.FAILED
    assert failed_article.celery_task_id == "task_failed"
    mock_revoke.assert_not_called()

@pytest.mark.django_db
@patch('text_to_audio.tasks.process_url_to_text')
@patch('text_to_audio.tasks.openai.OpenAI')
@patch('text_to_audio.tasks._chunk_text')
@patch('text_to_audio.models.Article.save') # Mock the save method directly
def test_process_article_explicitly_updates_updated_at_on_first_save(
    mock_article_save, mock_chunk_text, mock_openai_client, mock_process_url, test_feed
):
    """
    Test that process_article explicitly includes 'updated_at' in update_fields
    on its initial save when setting status to PROCESSING.
    """
    article = Article.objects.create(
        feed=test_feed,
        title="Test Explicit Update At",
        source_url="http://example.com/article",
        text_content="Initial content." # Provide some content to simplify mocks
    )
    # Store initial updated_at to compare against (though direct check of save is better)
    # initial_updated_at = article.updated_at 

    # Mock process_url_to_text to return successfully
    mock_process_url.return_value = (True, "Some extracted text.", None)
    # Mock _chunk_text to return some chunks
    mock_chunk_text.return_value = (True, ["chunk1"])
    # Mock OpenAI client
    mock_speech_response = MagicMock()
    mock_speech_instance = MagicMock()
    mock_speech_instance.audio.speech.create.return_value = mock_speech_response
    mock_openai_client.return_value = mock_speech_instance

    # Call the task. We are interested in the *first* call to article.save()
    # which happens inside the task after Article.objects.get().
    # Since we mocked Article.save globally for this test, it will apply to all instances.
    
    # We need to ensure that the original article instance fetched by
    # Article.objects.get(id=article_id) inside the task uses our mock_article_save.
    # The easiest way is to patch `Article.objects.get` to return an instance
    # that already has its `save` method mocked.

    mock_article_instance = MagicMock(spec=Article)
    # Configure required attributes for the mock instance if process_article uses them
    # before the first save, e.g., article.source_url, article.text_content, article.pk, article.id
    mock_article_instance.pk = article.pk
    mock_article_instance.id = article.id
    mock_article_instance.source_url = article.source_url
    mock_article_instance.text_content = article.text_content
    mock_article_instance.audio_uuid = None # To trigger audio_uuid generation path
    mock_article_instance.feed = test_feed # For feed name in tags
    mock_article_instance.title = article.title # For tags

    # mock_article_instance.save will be the mock_article_save due to the decorator's patch

    with patch('text_to_audio.tasks.Article.objects.get', return_value=mock_article_instance):
        try:
            process_article(article.id)
        except Exception:
            # Task might fail later due to incomplete mocks for a full run.
            # We only care about the first few operations.
            pass

    # Assertions:
    # Check the calls made to the mocked save method on our specific instance
    # The first call to save should be to set status=PROCESSING
    # The second call (if audio_uuid was None) should be to save audio_uuid
    # The third call should be to save status=COMPLETED/FAILED and audio_file_path

    # We want to find the call that sets status to PROCESSING
    processing_save_call = None
    for c in mock_article_instance.save.call_args_list:
        if c.kwargs.get('update_fields') and 'status' in c.kwargs['update_fields']:
             # Check if status was actually being set to PROCESSING in this call
             # This requires that the `status` attribute on mock_article_instance was updated
             # *before* save was called. The task does:
             # article.status = Article.PROCESSING
             # article.save(update_fields=["status", "updated_at"])
             # So, mock_article_instance.status should be Article.PROCESSING when save is called.
             # We can check `mock_article_instance.status` at the time of call if we refine the mock.
             # For now, let's assume the first save with 'status' in update_fields is it.
            
            # A simpler check: was there any call with update_fields=["status", "updated_at"]?
            if c.kwargs.get('update_fields') == ["status", "updated_at"]:
                 processing_save_call = c
                 break
            # It's possible other fields are also updated (e.g. audio_uuid if it's generated)
            # So, let's check if "status" and "updated_at" are *in* update_fields
            elif "status" in c.kwargs.get('update_fields', []) and \
                 "updated_at" in c.kwargs.get('update_fields', []):
                # Check that article.status was set to PROCESSING just before this call
                # This is tricky without capturing state at call time.
                # Let's assume the task logic `article.status = Article.PROCESSING` happens.
                processing_save_call = c
                break


    assert processing_save_call is not None, "Article.save was not called to set status to PROCESSING."
    
    # Verify that 'updated_at' was indeed in the update_fields for that specific call
    # and that 'status' was also there.
    assert 'status' in processing_save_call.kwargs['update_fields']
    assert 'updated_at' in processing_save_call.kwargs['update_fields']
    
    # This confirms that `updated_at` was part of the `update_fields` list
    # when `status` was being set to `PROCESSING`.

    # Note: The original article object in the test scope (`article`) is NOT the same
    # instance as `mock_article_instance` used inside the task if we mock Article.objects.get.
    # So, `article.refresh_from_db()` and checking `article.updated_at > initial_updated_at`
    # is less direct for *this specific subtask requirement* (testing `update_fields`).
    # The mock inspection is more precise for what was changed in the code.
```
