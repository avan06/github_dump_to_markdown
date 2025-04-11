# Overview

Fetch GitHub discussions or pullRequests or issues or commits and dump them as markdown files with author and timestamp information

- If you already have a GitHub Access Token, you likely don’t need to install the GitHub CLI (gh). This program primarily uses GitHub's GraphQL API to retrieve various data and convert it into markdown files.  
- However, if you plan to use the GitHub CLI to obtain the GitHub Access Token, you must first run gh auth login to ensure the gh auth token command generates a valid token:  
   $ gh auth login

## Usage
github_dump_to_markdown now supports determining the owner, repo, dumptype, and parameters specific to the dumptype through the URL.  
Specifically, it can extract:
- numbers for discussions, issues, or pull requests
- branch for commits list
- sha for single commit

This means that you can use a single URL to simplify your input, and the program will automatically extract the required information.  

Therefore, the following examples demonstrate various input methods that leverage URL parsing for different types of data retrieval.  
The program automatically adjusts its behavior based on the provided URL to fetch and dump the corresponding content (discussions, issues, pull requests, or commits).  

Examples:

1. Using explicit parameters for owner, repo, numbers, and dumptype:  
   \$ python github_dump_to_markdown.py --token $(gh auth token) \  
       --owner owner \  
       --repo repo \  
       --numbers 1234 1235 1240-1290 \  
       --dumptype discussion  

2. Using a repository URL to determine owner and repo:  
   \$ python github_dump_to_markdown.py --token $(gh auth token) \  
       --url https://github.com/owner/repo \  
       --numbers 1234 1235 1240-1290 \  
       --dumptype discussion  

3. Using a URL with dumptype included:  
   \$ python github_dump_to_markdown.py --token $(gh auth token) \  
       --url https://github.com/owner/repo/discussions \  
       --numbers 1234 1235 1240-1290  

4. Using a URL with both dumptype and a single number:  
   \$ python github_dump_to_markdown.py --token $(gh auth token) \  
       --url https://github.com/owner/repo/discussions/1234 \  
       --numbers 1235 1240-1290  

5. Using only a URL to determine all parameters:  
   only that single number (1234 in this case) will be extracted.  
   \$ python github_dump_to_markdown.py --token $(gh auth token) \  
       --url https://github.com/owner/repo/discussions/1234  

6. Using explicit parameters for owner, repo, dumptype, and branch for commits:
   $ python github_dump_to_markdown.py --token $(gh auth token) \
       --owner owner \
       --repo repo \
       --dumptype commits \
       --branch main

7. Using a repository URL to determine owner and repo, with dumptype and branch for commits:
   $ python github_dump_to_markdown.py --token $(gh auth token) \
       --url https://github.com/owner/repo \
       --dumptype commits \
       --branch main

8. Using a URL with dumptype and branch included for commits:
   $ python github_dump_to_markdown.py --token $(gh auth token) \
       --url https://github.com/owner/repo/commits/main


## options

-  -t, --token  
GitHub Access Token  
If this option is not provided, the program will attempt to obtain a GitHub authentication token using the `gh auth login` command from the GitHub CLI (requires the `gh` CLI to be installed).  

- --url  
GitHub Repository URL. Automatically extracts `owner`, `repo`, `dumptype`, and either `numbers` (for discussions, issues, or pull requests) or `branch` (for commits) or `sha` (for commit) based on the provided URL  

-  --owner    
GitHub Repository Owner, required unless `--url` is provided  

-  --repo    
GitHub Repository Name, required unless `--url` is provided  

- -dt, --dumptype  
Enter discussion or pullRequest or issue or commits or commit, default discussion  

-  -n, --numbers  
GitHub Discussion or PullRequest or Issue Numbers (space-separated, supports ranges like '1000-1200')  

- --branch  
Git branch is required when `dumptype` is set to `commits` or provided through `--url`

- --sha  
Git commit sha is required when `dumptype` is set to `commit` or provided through `--url`  

- -o, --output-dir  
Output directory for markdown files, default docs  

-  --api  
GitHub GraphQL endpoint, default https://api.github.com/graphql  

### Note:
- If `--url` is provided, the program will automatically determine the `owner`, `repo`, `dumptype`, and either `numbers` (for discussions, issues, or pull requests) or `branch` (for commits) or `sha` (for commit) based on the provided URL
- If numbers are provided both via `--url` and `--numbers`, the program will combine them.


## Credits & Reference
https://github.com/intel/dffml/blob/main/scripts/dump_discussion.py
https://github.com/intel/dffml/blob/main/scripts/discussion_dump_to_markdown.py
https://github.com/orgs/community/discussions/3315#discussioncomment-3094387