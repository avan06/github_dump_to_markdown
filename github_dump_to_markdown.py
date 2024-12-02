"""
Fetch GitHub discussions or pullRequests or issues and dump them as markdown files with author and timestamp information

If you already have a GitHub Access Token, you likely don’t need to install the GitHub CLI (gh). This program primarily uses GitHub's GraphQL API to retrieve various data and convert it into markdown files.

Usage:
$ gh auth login
$ python github_dump_to_markdown.py --token $(gh auth token) \
    --owner intel \
    --repo dffml \
    --numbers 1234 1235 1240-1290 \
    --dumptype discussion

$ github_dump_to_markdown.py [-h] [-t TOKEN] [--owner OWNER] [--repo REPO] [--url URL] -n NUMBERS [NUMBERS ...]
                                  [--api API] [-o OUTPUT_DIR] [-dt DUMPTYPE]

options:
  -h, --help       show this help message and exit
  -t, --token      GitHub Access Token: If this parameter is not provided, the program will attempt to obtain a
                   GitHub authentication token using the `gh auth login` command from the GitHub CLI (requires the `gh` CLI to be installed).
  --owner          GitHub Repository Owner, required
  --repo           GitHub Repository Name, required
  --url            GitHub Repository Url, If `--url` is provided, `--owner` and `--repo` are not required
  -n, --numbers    GitHub Discussion or PullRequest or Issue Numbers (space-separated, supports ranges like '1000-1200')
  --api            GitHub GraphQL endpoint, default https://api.github.com/graphql
  -o, --output-dir Output directory for markdown files, default docs
  -dt, --dumptype  Enter discussion or pullRequest or issue, default discussion

Credits & Reference
https://github.com/intel/dffml/blob/main/scripts/dump_discussion.py
https://github.com/intel/dffml/blob/main/scripts/discussion_dump_to_markdown.py
https://github.com/orgs/community/discussions/3315#discussioncomment-3094387
"""
import sys
import re
import asyncio
import aiohttp
import pathlib
import argparse
import traceback
import subprocess
from dataclasses import dataclass, field
from typing import List
from datetime import datetime
from urllib.parse import urlparse

@dataclass
class Reply:
    id: str
    body: str
    author: str
    created_at: datetime
    
@dataclass
class Comment:
    id: str
    body: str
    author: str
    created_at: datetime
    replies: List[Reply] = field(default_factory=list)

@dataclass
class QueryResult:
    url: str
    dumptype: str
    number: int
    state: str
    body: str
    title: str
    author: str
    created_at: datetime
    comments: List[Comment] = field(default_factory=list)

async def fetch_github_data(session, graphql_url, token, owner, repo, number, dumptype):
    """
    Fetch discussion or pullRequest or issue data from GitHub GraphQL API
    
    Returns:
        Discussion object if successful
        None if discussion not found or error occurs
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    querypullRequests = """
    query($owner: String!, $repo: String!, $number: Int!, $commentsCursor: String) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
          title
          body
          author {
            login
          }
          createdAt
          state
          url
          comments(first: 100, after: $commentsCursor) {
            totalCount
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              body
              author {
                login
              }
              createdAt
            }
          }
        }
      }
    }
    """

    queryIssues = """
    query($owner: String!, $repo: String!, $number: Int!, $commentsCursor: String) {
      repository(owner: $owner, name: $repo) {
        issue(number: $number) {
          title
          body
          author {
            login
          }
          createdAt
          state
          url
          comments(first: 100, after: $commentsCursor) {
            totalCount
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              body
              author {
                login
              }
              createdAt
            }
          }
        }
      }
    }
    """

    queryDiscussion = """
    query($owner: String!, $repo: String!, $number: Int!, $commentsCursor: String, $repliesCursor: String) {
      repository(owner: $owner, name: $repo) {
        discussion(number: $number) {
          title
          body
          author {
            login
          }
          createdAt
          url
          comments(first: 100, after: $commentsCursor) {
            totalCount
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              body
              author {
                login
              }
              createdAt
              replies(first: 100, after: $repliesCursor) {
                totalCount
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  id
                  body
                  author {
                    login
                  }
                  createdAt
                }
              }
            }
          }
        }
      }
    }
    """

    variables = {
        "owner": owner,
        "repo": repo,
        "number": number
    }

    try:
        comments_data = []
        has_next_page = True
        comments_cursor = None

        query = ""
        if dumptype == "discussion":
            query = queryDiscussion
        elif dumptype == "pullRequest": 
            query = querypullRequests
        elif dumptype == "issue": 
            query = queryIssues

        while has_next_page:
            variables["commentsCursor"] = comments_cursor
            response = await session.post(graphql_url, headers=headers, json={"query": query, "variables": variables})
            result = await response.json()

            # Check if discussion exists
            if not result.get("data", {}).get("repository", {}).get(dumptype):
                # print(f"Discussion {number:03} not found.")
                if result.get("errors", {}):
                    if result["errors"][0].get("type", {}) != "NOT_FOUND":
                        print("Error: " + str(result["errors"]))
                return None

            queryResult = result["data"]["repository"][dumptype]
            result_url = queryResult["url"]
            result_state = queryResult["state"] if dumptype != "discussion" else ""
            result_title = queryResult["title"]
            result_body = queryResult["body"]
            result_author = queryResult["author"]["login"] if queryResult["author"] else "None"
            result_created_at = datetime.fromisoformat(queryResult["createdAt"].replace('Z', '+00:00'))
            comments = queryResult["comments"]["nodes"]
            has_next_page = queryResult["comments"]["pageInfo"]["hasNextPage"]
            comments_cursor = queryResult["comments"]["pageInfo"]["endCursor"]

            for comment in comments:
                if not comment:
                    continue
                comment_id = comment["id"]
                comment_body = comment["body"]
                comment_author = comment["author"]["login"] if comment["author"] else "None"
                comment_created_at = datetime.fromisoformat(comment["createdAt"].replace('Z', '+00:00'))
                replies = []

                if dumptype == "discussion":
                    for reply in comment["replies"]["nodes"]:
                        reply_data = Reply(
                            id=reply["id"],
                            body=reply["body"],
                            author=reply["author"]["login"] if reply["author"] else "None",
                            created_at=datetime.fromisoformat(reply["createdAt"].replace('Z', '+00:00'))
                        )
                        replies.append(reply_data)

                comments_data.append(Comment(
                    id=comment_id,
                    body=comment_body, 
                    author=comment_author, 
                    created_at=comment_created_at,
                    replies=replies
                ))

        return QueryResult(
            url=result_url,
            dumptype=dumptype,
            number=number,
            state=result_state,
            title=result_title, 
            body=result_body, 
            author=result_author,
            created_at=result_created_at,
            comments=comments_data
        )
    except Exception as e:
        print(traceback.format_exc())
        print(f"Error fetching {dumptype} {number:03}: {e}")
        return None

def output_markdown(queryResult: QueryResult, output_directory: pathlib.Path, number: int):
    """
    Convert discussion data to a single consolidated markdown file
    
    Args:
        discussion (Discussion): The full discussion data
        output_directory (pathlib.Path): Directory to save the markdown file
        number (int): The discussion or pullRequest number for naming
    """
    def create_filename(dumptype: str, number: int, title: str) -> str:
        """
        Create a filename based on number and title
        """
        def sanitize_filename(filename: str, max_length=120) -> str:
            """
            Convert a string to a safe filename
            - Replace non-alphanumeric characters with underscores
            - Ensure filename is UTF-8 compatible
            - Limit length to prevent issue
            """
            # Remove or replace characters that are problematic in filenames
            filename = re.sub(r'[^\w\-_. ]', '_', filename)

            if len(filename) <= max_length:
                return filename

            # Truncates the filename to a specified maximum length without breaking words.
            truncated = filename[:max_length]
            last_space = max(truncated.rfind(" "), truncated.rfind("_"), truncated.rfind("-"))
            if last_space > 0:
                return truncated[:last_space].rstrip("_- ")
            return truncated
        # Start with discussion number
        base_filename = f"{dumptype}{number:03}_"
    
        # Add sanitized title
        title_part = sanitize_filename(title.split('\n')[0])
        filename = base_filename + title_part

        return filename
    # Create the output directory if it doesn't exist
    output_directory.mkdir(parents=True, exist_ok=True)

    # Generate main filename
    base_filename = create_filename(queryResult.dumptype, number, queryResult.title)
    
    # Create consolidated markdown file path
    markdown_path = output_directory.joinpath(f"{base_filename}.md")
    
    # Prepare the markdown content
    markdown_content = []
    
    # Add discussion title, author, and timestamp
    markdown_content.append(f"# [{queryResult.title}]({queryResult.url})\n")
    markdown_content.append(f"**@{queryResult.author}** &emsp; **Created at**: {queryResult.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}  &emsp; {queryResult.state}\n\n")
    markdown_content.append(f"{queryResult.body}\n")
    markdown_content.append("---\n")
    
    # Add comments and their replies
    for i, comment in enumerate(queryResult.comments):
        # Add comment header, author, and timestamp
        markdown_content.append(f"## **Comment {i+1}**, **@{comment.author}** &emsp; **at**: {comment.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n")
        markdown_content.append(f"{comment.body}\n")
        
        # Add replies to this comment
        if comment.replies:
            for j, reply in enumerate(comment.replies):
                markdown_content.append(f"### **Reply {j+1}**, **@{reply.author}** &emsp; **at**: {reply.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n")
                markdown_content.append(f"{reply.body}\n")
        
        # Add separator between comments
        markdown_content.append("---\n")
    
    # Write the consolidated markdown file
    full_markdown_text = "\n".join(markdown_content)
    markdown_path.write_text(full_markdown_text, encoding='utf-8')
    
    print(f"Created file: {markdown_path}")

async def main():
    parser = argparse.ArgumentParser(description="Fetch and dump GitHub discussions or pullRequests or issues data")
    def get_gh_token():
        """
        Retrieve the GitHub authentication token, compatible with both Windows and Linux.
        Using the "gh auth login" command from the GitHub CLI (requires the gh CLI to be installed).
        """
        try:
            # Use subprocess to capture the output of `gh auth token`
            result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print("\nFailed to retrieve GitHub Token. Please ensure you are logged in using GitHub CLI (gh auth login).\n")
            print(f"Error message: {e.stderr.strip()}\n")
            parser.print_help()
            sys.exit(1)

    def parse_github_url(url):
        # Parse the URL into components using urlparse
        parsed_url = urlparse(url)
    
        # Check if the domain is GitHub
        if "github.com" not in parsed_url.netloc:
            print(f"\nInvalid GitHub URL `--url`: {url}\n")
            parser.print_help()
            sys.exit(1)
    
        # Split the path to extract the owner and repository
        path_parts = parsed_url.path.strip("/").split("/")
        if len(path_parts) < 2:
            print(f"\nInvalid GitHub repository URL `--url`: {url}\n")
            parser.print_help()
            sys.exit(1)
    
        owner = path_parts[0]
        repo = path_parts[1]
        return owner, repo

    def parse_range(value):
        """Parse a single value or a range (e.g., '1000-1200')"""
        try:
            if '-' in value:
                start, end = map(int, value.split('-'))
                if start > end:
                    raise argparse.ArgumentTypeError(f"Invalid range: {value}")
                return list(range(start, end + 1))
            else:
                return [int(value)]
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid input: {value}")

    parser.add_argument("-t", "--token", help="GitHub Access Token: If this parameter is not provided, the program will attempt to obtain a GitHub authentication token using the `gh auth login` command from the GitHub CLI (requires the `gh` CLI to be installed).")
    parser.add_argument("--owner", help="GitHub Repository Owner, required")
    parser.add_argument("--repo", help="GitHub Repository Name, required")
    parser.add_argument("--url", help="GitHub Repository Url, If `--url` is provided, `--owner` and `--repo` are not required")
    parser.add_argument("-n", "--numbers", nargs='+', type=parse_range, help="GitHub Discussion or PullRequest or Issue Numbers (space-separated, supports ranges like '1000-1200')", required=True)
    parser.add_argument("--api", help="GitHub GraphQL endpoint, default https://api.github.com/graphql", default="https://api.github.com/graphql")
    parser.add_argument("-o", "--output-dir", help="Output directory for markdown files, default docs", default="docs")
    parser.add_argument("-dt", "--dumptype", help="Enter discussion or pullRequest or issue, default discussion", default="discussion")
    args = parser.parse_args()

    if not args.token:
        # Attempt to obtain a GitHub authentication token using the gh auth login command from the GitHub CLI 
        args.token = get_gh_token()

    if args.url:
        args.owner, args.repo = parse_github_url(args.url)

    if not args.owner or not args.repo:
        print("\nError: `--owner` and `--repo` are required options, or you can specify `--url` to automatically retrieve the owner and repo.\n")
        parser.print_help()
        sys.exit(1)

    # Convert discussion numbers to flatten list
    numbers = [item for sublist in args.numbers for item in sublist]
    # Convert output directory to Path object
    output_dir = pathlib.Path(args.output_dir) / args.repo

    args.dumptype = args.dumptype

    async with aiohttp.ClientSession(trust_env=True) as session:
        # Process each discussion number
        discussions_processed = 0
        discussions_failed = 0

        for number in numbers:
            try:
                # Fetch discussion data
                discussion_data = await fetch_github_data(
                    session, 
                    args.api,
                    args.token, 
                    args.owner, 
                    args.repo, 
                    number,
                    args.dumptype
                )
                
                # Output as markdown file if discussion exists
                if discussion_data:
                    output_markdown(discussion_data, output_dir, number)
                    discussions_processed += 1
                else:
                    discussions_failed += 1
            except Exception as e:
                print(traceback.format_exc())
                print(f"Error processing discussion {number:03}: {e}")
                discussions_failed += 1

        # Print summary
        print(f"\nProcessing complete.")
        print(f"Discussions processed successfully: {discussions_processed}")
        print(f"Discussions failed: {discussions_failed}")

if __name__ == "__main__":
    asyncio.run(main())