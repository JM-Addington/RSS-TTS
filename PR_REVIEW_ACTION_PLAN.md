# PR Review Action Plan

## Overview
This document outlines the comprehensive plan to address all action items identified in the PR review conducted by Mike and Joe. The issues are categorized by severity with specific implementation steps.

## Critical Issues (Must Fix Immediately) 🔴

### 1. Destructive Delete in ArticleDeleteView
**Location**: `text_to_audio/views.py:650-651`  
**Risk**: Data loss - deletes entire `media/articles` directory  
**Current Code**:
```python
dirname = os.path.dirname(file_path_to_delete)
shutil.rmtree(dirname, ignore_errors=True)
```
**Fix**: Replace with simple file deletion:
```python
try:
    os.unlink(file_path_to_delete)
except (OSError, FileNotFoundError, PermissionError) as e:
    logger.warning(f"Error deleting file {file_path_to_delete}: {e}")
```

### 2. Missing OpenAI Model Settings
**Location**: `rss_tts/settings.py`  
**Problem**: `OPENAI_ANALYSIS_MODEL` and `OPENAI_CLASSIFICATION_MODEL` are referenced but not defined  
**Fix**: Add to settings.py after line 24:
```python
OPENAI_ANALYSIS_MODEL = os.environ.get("OPENAI_ANALYSIS_MODEL", "gpt-4o-mini")
OPENAI_CLASSIFICATION_MODEL = os.environ.get("OPENAI_CLASSIFICATION_MODEL", "gpt-4o-mini")
```

### 3. Non-existent TTS Parameter
**Location**: `text_to_audio/tasks.py:643`  
**Problem**: `voice_instructions` is not a valid OpenAI TTS API parameter  
**Fix**: Remove lines 642-643 that add this parameter

### 4. Verify Missing Migrations
**Status**: ✅ VERIFIED - migrations exist in `text_to_audio/migrations/`
- `0002_sync_voice_fields.py` ✅
- `0003_set_feeds_to_auto_voice.py` ✅

## Major Issues 🟡

### 5. Remove Unused ARTICLE_STORAGE_DIR Setting
**Location**: `rss_tts/settings.py:142`  
**Fix**: Delete this line and any code that references it

### 6. Update Feed.voice_mode Default
**Location**: `text_to_audio/models.py:56`  
**Current**: `default=VOICE_MODE_SINGLE_DEFAULT`  
**Fix**: Change to `default=VOICE_MODE_AUTO`  
**Note**: Migrations already exist to handle existing data

### 7. Reduce MAX_ANALYSIS_WORDS
**Location**: `text_to_audio/services/content_analysis.py:7`  
**Current**: `MAX_ANALYSIS_WORDS = 750_000`  
**Fix**: Change to `MAX_ANALYSIS_WORDS = 8_000`  
**Enhancement**: Make configurable via settings

### 8. Optimize _chunk_text for Large Texts
**Location**: `text_to_audio/tasks.py` (_chunk_text function)  
**Issue**: Quadratic complexity on 30k-word inputs  
**Fix**: Implement linear scanning with early termination

### 9. Simplify Path Resolution
**Location**: `text_to_audio/views.py` (ArticleMediaView and ArticleDeleteView)  
**Fix**: Add deprecation warnings for legacy paths, plan migration

## Minor Improvements 🟢

### 10. Add choices to UserVoicePreset.voice_id
**Location**: `text_to_audio/models.py`  
**Fix**: Add `choices=Article.VOICE_CHOICES` to field definition

### 11. Cache get_available_voice_modes
**Location**: `text_to_audio/services/voice_configuration.py`  
**Fix**: Use `@cached_property` or module-level constant

### 12. Fix test patching
**Location**: Various test files  
**Fix**: Update patch paths to be more robust

### 13. Clean up duplicate forms
**Fix**: Remove `forms.py` if `forms_improved.py` is the active version

### 14. Update README
**Fix**: Clarify SQLite vs PostgreSQL usage

## Implementation Sequence

### Phase 1: Critical Fixes (Day 1)
1. **Fix ArticleDeleteView destructive delete** - HIGHEST PRIORITY
2. **Add missing OpenAI model settings**
3. **Remove voice_instructions parameter**

### Phase 2: Major Fixes (Day 2-3)
4. **Remove ARTICLE_STORAGE_DIR setting**
5. **Update Feed.voice_mode default**
6. **Reduce MAX_ANALYSIS_WORDS**
7. **Optimize _chunk_text performance**
8. **Add path resolution deprecation warnings**

### Phase 3: Minor Improvements (Day 4-5)
9. **Code quality improvements**
10. **Test improvements**
11. **Documentation updates**

## Action Checklist

### Critical (Day 1) ✅ COMPLETED
- [x] Fix destructive delete in `ArticleDeleteView`
- [x] Add `OPENAI_ANALYSIS_MODEL` and `OPENAI_CLASSIFICATION_MODEL` to settings
- [x] Remove `voice_instructions` kwarg from TTS calls

### Major (Day 2-3) ✅ COMPLETED
- [x] Remove `ARTICLE_STORAGE_DIR` setting and references
- [x] Change `Feed.voice_mode` default to `VOICE_MODE_AUTO`
- [x] Reduce `MAX_ANALYSIS_WORDS` to 8,000 and make configurable
- [x] Optimize `_chunk_text` for 30k word documents (linear scanning approach)
- [x] Add deprecation warnings to legacy path resolution code

### Minor (Day 4-5)
- [ ] Add choices to `UserVoicePreset.voice_id`
- [ ] Cache `get_available_voice_modes`
- [ ] Fix test patching issues
- [ ] Consolidate forms.py/forms_improved.py
- [ ] Update README for database clarity
- [ ] Add `.pytest_cache/` to `.gitignore`
- [ ] Add golden path integration test

## Testing Strategy

### Unit Tests
- Update existing tests to verify fixes
- Add specific tests for ArticleDeleteView file deletion
- Test voice mode defaults

### Integration Tests
- Test complete article lifecycle with new defaults
- Verify path resolution works correctly
- Test voice parameter generation with reduced context

### Manual Testing
- Test article deletion with various file structures
- Verify no data loss scenarios
- Test voice mode functionality end-to-end

### Performance Testing
- Profile `_chunk_text` with 30k word documents
- Measure improvement in processing time
- Verify reduced OpenAI API costs

## Risk Mitigation

### Data Loss Prevention
- **Backup Strategy**: Create backup of `media/articles` before deployment
- **Rollback Plan**: Tag current version for quick rollback if needed
- **Testing**: Thoroughly test deletion logic in staging environment

### Deployment Strategy
- **Staged Deployment**: Deploy critical fixes first, monitor, then proceed
- **Monitoring**: Watch for errors in logs after each deployment phase
- **Gradual Rollout**: Test with subset of users first

## Success Criteria

### Critical Fixes
- ✅ No data loss from article deletion
- ✅ No runtime errors from missing settings
- ✅ TTS API calls succeed without invalid parameters

### Major Fixes
- ✅ Reduced OpenAI API costs from smaller context windows
- ✅ Better performance on large documents
- ✅ Consistent voice mode behavior

### Minor Improvements
- ✅ Cleaner codebase with removed deprecated code
- ✅ Better test coverage and reliability
- ✅ Updated documentation matches implementation

## Post-Implementation Verification

1. **Smoke Tests**: Verify basic functionality works
2. **Regression Tests**: Ensure no existing functionality is broken
3. **Performance Tests**: Confirm improvements in processing time and costs
4. **User Acceptance**: Verify user-facing features work as expected

---

**Document Status**: Draft  
**Created**: 2025-05-29  
**Last Updated**: 2025-05-29  
**Approved By**: Pending implementation