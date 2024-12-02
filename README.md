# Overview

Fetch GitHub discussions or pullRequests or issues and dump them as markdown files with author and timestamp information

- If you already have a GitHub Access Token, you likely don’t need to install the GitHub CLI (gh). This program primarily uses GitHub's GraphQL API to retrieve various data and convert it into markdown files.

## Usage
$ gh auth login  
$ python github_dump.py --token $(gh auth token) \  
    --owner intel \  
    --repo dffml \  
    --numbers 1234 1235 1240-1290 \  
    --dumptype discussion

## options

-  -t, --token  
GitHub Access Token  
If this option is not provided, the program will attempt to obtain a GitHub authentication token using the `gh auth login` command from the GitHub CLI (requires the `gh` CLI to be installed).  
-  --owner    
GitHub Repository Owner, required  

-  --repo    
GitHub Repository Name, required  

- --url
GitHub Repository Url, If `--url` is provided, `--owner` and `--repo` are not required  

-  -n, --numbers  
GitHub Discussion or PullRequest or Issue Numbers (space-separated, supports ranges like '1000-1200')  

-  --api  
GitHub GraphQL endpoint, default https://api.github.com/graphql  

-  --output-dir  
Output directory for markdown files, default docs  

-  --dumptype  
Enter discussion or pullRequest or issue, default discussion  

## Credits & Reference
https://github.com/intel/dffml/blob/main/scripts/dump_discussion.py
https://github.com/intel/dffml/blob/main/scripts/discussion_dump_to_markdown.py
https://github.com/orgs/community/discussions/3315#discussioncomment-3094387