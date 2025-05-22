# GitHub Project Board Setup

This document outlines the structure of our GitHub Project board for the RSS-TTS project.

## Project Board Structure

Our GitHub Project board is organized by phases and epics, following the structure defined in the [PROJECT_PLAN.md](PROJECT_PLAN.md) file.

### Milestones

We have created the following milestones in GitHub:

1. **Phase 0: Initial Setup and Infrastructure**
   - Deadline: [Date]
   - Description: Establish the development environment, repository, and base project structure

2. **Phase 1: MVP – Core Functionality and Private RSS**
   - Deadline: [Date]
   - Description: Deliver a Minimum Viable Product where users can log in, submit a URL or text, have it converted to an MP3, and access their audio via a private RSS feed

3. **Phase 2: Enhanced Features and Refinements**
   - Deadline: [Date]
   - Description: Add voice customization, advanced parsing, usage analytics, and multi-feed support

### Epics and Issues

Each phase is broken down into epics, and each epic contains multiple issues:

#### Phase 0 Epics

1. **Epic 0.1: Repository & Project Management Setup**
   - Initialize GitHub Repository
   - Define Coding Standards & CI

2. **Epic 0.2: Dockerized Development Environment**
   - Write Dockerfile for Django App
   - Write Dockerfile for Celery Worker
   - Docker Compose Configuration
   - Environment Variables & Config

3. **Epic 0.3: Base Django Project Initialization**
   - Start Django Project
   - User Authentication Setup
   - Bootstrap Frontend Integration
   - Initial GitHub Issues & Milestone

#### Phase 1 Epics

1. **Epic 1.1: User Accounts & Feed Models**
2. **Epic 1.2: Article Submission & Text Extraction**
3. **Epic 1.3: Text-to-Speech Conversion Pipeline**
4. **Epic 1.4: RSS Feed Generation**
5. **Epic 1.5: Frontend UI & UX**

#### Phase 2 Epics

1. **Epic 2.1: Voice Tone Detection & Customization**
2. **Epic 2.2: Smarter Content Parsing**
3. **Epic 2.3: Usage Analytics & Monitoring**
4. **Epic 2.4: Multiple Feeds & Organization**
5. **Epic 2.5: Polishing and Documentation**

## Project Board Columns

Our board uses the following columns:

1. **Backlog**: Issues that have been created but not yet scheduled for work
2. **To Do**: Issues scheduled for the current sprint/iteration
3. **In Progress**: Issues currently being worked on
4. **Review**: Issues with an open PR awaiting review
5. **Done**: Completed issues

## Labels

We use the following labels to categorize issues:

- `epic`: Denotes an epic that contains multiple issues
- `feature`: New functionality
- `enhancement`: Improvements to existing functionality
- `bug`: Something isn't working as expected
- `documentation`: Documentation-related tasks
- `testing`: Testing-related tasks
- `devops`: Infrastructure, CI/CD, and deployment tasks
- `phase-0`, `phase-1`, `phase-2`: Indicates which phase the issue belongs to

## Issue Templates

We've created issue templates for common types of tasks:

1. **Feature Request**: For new features
2. **Bug Report**: For reporting bugs
3. **Epic**: For creating new epics
4. **Documentation**: For documentation tasks

## Usage Guidelines

1. **Creating Issues**:
   - Always assign issues to a milestone and relevant epic
   - Add appropriate labels
   - Include clear acceptance criteria

2. **Working on Issues**:
   - Assign yourself to an issue before starting work
   - Move the issue to "In Progress"
   - Create a branch using the naming convention specified in AGENTS.md

3. **Completing Issues**:
   - Create a pull request
   - Move the issue to "Review"
   - Once the PR is merged, move the issue to "Done"

4. **Tracking Progress**:
   - Use the project board to track overall project progress
   - Review the board during team meetings
   - Update issue status regularly
