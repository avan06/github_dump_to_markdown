"""
Fetch GitHub discussions or pullRequests or issues or commits and dump them as markdown files with author and timestamp information

If you already have a GitHub Access Token, you likely don’t need to install the GitHub CLI (gh). This program primarily uses GitHub's GraphQL API to retrieve various data and convert it into markdown files.
However, if you plan to use the GitHub CLI to obtain the GitHub Access Token, you must first run gh auth login to ensure the gh auth token command generates a valid token:
   $ gh auth login

Usage:
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
   $ python github_dump_to_markdown.py --token $(gh auth token) \
       --owner owner \
       --repo repo \
       --numbers 1234 1235 1240-1290 \
       --dumptype discussion

2. Using a repository URL to determine owner and repo:
   $ python github_dump_to_markdown.py --token $(gh auth token) \
       --url https://github.com/owner/repo \
       --numbers 1234 1235 1240-1290 \
       --dumptype discussion

3. Using a URL with dumptype included:
   $ python github_dump_to_markdown.py --token $(gh auth token) \
       --url https://github.com/owner/repo/discussions \
       --numbers 1234 1235 1240-1290

4. Using a URL with both dumptype and a single number:
   $ python github_dump_to_markdown.py --token $(gh auth token) \
       --url https://github.com/owner/repo/discussions/1234 \
       --numbers 1235 1240-1290

5. Using only a URL to determine all parameters:
   only that single number (1234 in this case) will be extracted.
   $ python github_dump_to_markdown.py --token $(gh auth token) \
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


$ github_dump_to_markdown.py [-h] [-t TOKEN] [--owner OWNER] [--repo REPO] [--url URL] [-n NUMBERS [NUMBERS ...]]
                             [--api API] [-o OUTPUT_DIR] [-dt DUMPTYPE] [--branch BRANCH] [--sha SHA]

Note:
- If `--url` is provided, the program will automatically determine the `owner`, `repo`, `dumptype`, and either `numbers` (for discussions, issues, or pull requests) or `branch` (for commits) or `sha` (for commit) based on the provided URL
- If numbers are provided both via `--url` and `--numbers`, the program will combine them.

Options:
  -h, --help       show this help message and exit
  -t, --token      GitHub Access Token: If this parameter is not provided, the program will attempt to obtain a
                   GitHub authentication token using the `gh auth login` command from the GitHub CLI (requires the `gh` CLI to be installed).
  --url            GitHub Repository URL. Automatically extracts `owner`, `repo`, `dumptype`, and either 
                   `numbers` (for discussions, issues, or pull requests) or 
                   `branch` (for commits) or `sha` (for commit) based on the provided URL
  --owner          GitHub Repository Owner, required unless `--url` is provided
  --repo           GitHub Repository Name, required unless `--url` is provided
  -dt, --dumptype  Enter discussion or pullRequest or issue or commits or commit, default discussion
  -n, --numbers    GitHub Discussion or PullRequest or Issue Numbers (space-separated, supports ranges like '1000-1200')
  --branch         Git branch is required when `dumptype` is set to `commits` or provided through `--url`
  --sha            Git commit sha is required when `dumptype` is set to `commit` or provided through `--url`
  -o, --output-dir Output directory for markdown files, default docs
  --api            GitHub GraphQL endpoint, default https://api.github.com/graphql

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

@dataclass
class CommitQueryResult:
  dumptype: str
  oid: str
  message: str
  committedDate: datetime
  author: str

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

queryCommits = """
query($owner: String!, $repo: String!, $branch: String!, $historyCursor: String) {
  repository(owner: $owner, name: $repo) {
    ref(qualifiedName: $branch) {
      target {
        ... on Commit {
          history(first: 100, after: $historyCursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            edges {
              node {
                message
                oid
                committedDate
                author {
                  name
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

queryCommitBySHA = """
query($owner: String!, $repo: String!, $sha: GitObjectID!) {
  repository(owner: $owner, name: $repo) {
    object(oid: $sha) {
      ... on Commit {
        message
        oid
        committedDate
        author {
          name
        }
        url
      }
    }
  }
}
"""

async def fetch_github_data(session, graphql_url, token, owner, repo, dumptype, number=None, branch=None, sha=None):
  """
  Fetch discussion or pullRequest or issue or commits or commit data from GitHub GraphQL API

  Returns:
    QueryResult or CommitQueryResult object if successful
    None if data not found or error occurs
  """
  headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
  }

  variables = {
    "owner": owner,
    "repo": repo,
  }
  if dumptype in ["discussion", "pullRequest", "issue"]:
    variables["number"] = number
  elif dumptype == "commits":
    variables["branch"] = branch
  elif dumptype == "commit":
    variables["sha"] = sha

  try:
    query = ""
    if dumptype == "discussion":
      query = queryDiscussion
    elif dumptype == "pullRequest":
      query = querypullRequests
    elif dumptype == "issue":
      query = queryIssues
    elif dumptype == "commits":
      query = queryCommits
    elif dumptype == "commit":
      query = queryCommitBySHA

    response = await session.post(graphql_url, headers=headers, json={"query": query, "variables": variables})
    result = await response.json()

    if result.get("errors"):
      print("GraphQL Errors: " + str(result["errors"]))
      return None

    if dumptype in ["discussion", "pullRequest", "issue"]:
      if not result.get("data", {}).get("repository", {}).get(dumptype):
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

      comments_data = []
      if "comments" in queryResult: # discussions, issues, pullRequests have comments
        has_next_page = True
        comments_cursor = None
        while has_next_page:
          queryResult = result["data"]["repository"][dumptype]
          comments = queryResult["comments"]["nodes"]

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

          has_next_page = queryResult["comments"]["pageInfo"]["hasNextPage"]
          comments_cursor = queryResult["comments"]["pageInfo"]["endCursor"]
          if has_next_page:
            variables["commentsCursor"] = comments_cursor
            response = await session.post(graphql_url, headers=headers, json={"query": query, "variables": variables})
            result = await response.json()

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
    elif dumptype == "commits":
      commits_data = []
      has_next_page = True
      history_cursor = None
      while has_next_page:
        if result.get("data", {}).get("repository", {}).get("ref"):
          history_data = result["data"]["repository"]["ref"]["target"]["history"]
          history_edges = history_data["edges"]
          for edge in history_edges:
            node = edge["node"]
            commit_data = CommitQueryResult(
              dumptype=dumptype,
              oid=node["oid"],
              message=node["message"],
              committedDate=datetime.fromisoformat(node["committedDate"].replace('Z', '+00:00')),
              author=node["author"]["name"] if node["author"] else "None",
            )
            commits_data.append(commit_data)

          has_next_page = history_data["pageInfo"]["hasNextPage"]
          history_cursor = history_data["pageInfo"]["endCursor"]
        else:
          return None

        if has_next_page:
          variables["historyCursor"] = history_cursor
          response = await session.post(graphql_url, headers=headers, json={"query": query, "variables": variables})
          result = await response.json()
          if result.get("errors"):
            print("GraphQL Errors: " + str(result["errors"]))
            return None

      return commits_data # return list of CommitQueryResult
    elif dumptype == "commit":
      if result.get("data", {}).get("repository", {}).get("object"):
        commit_object = result["data"]["repository"]["object"]
        commit_data = CommitQueryResult(
          dumptype=dumptype,
          oid=commit_object["oid"],
          message=commit_object["message"],
          committedDate=datetime.fromisoformat(commit_object["committedDate"].replace('Z', '+00:00')),
          author=commit_object["author"]["name"] if commit_object["author"] else "None",
        )
        return commit_data # return single CommitQueryResult
      else:
        return None

  except Exception as e:
    print(traceback.format_exc())
    print(f"Error fetching {dumptype} {number if number is not None else branch or sha}: {e}")
    return None

def output_markdown(queryResult: QueryResult, output_directory: pathlib.Path, number: int):
  """
  Convert discussion/issue/pr data to a single consolidated markdown file

  Args:
    queryResult (QueryResult): The query result data
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
  markdown_content.append(f"**@{queryResult.author}**   **Created at**: {queryResult.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}    {queryResult.state}\n\n")
  markdown_content.append(f"{queryResult.body}\n")
  markdown_content.append("---\n")

  # Add comments and their replies
  for i, comment in enumerate(queryResult.comments):
    # Add comment header, author, and timestamp
    markdown_content.append(f"## **Comment {i+1}**, **@{comment.author}**   **at**: {comment.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n")
    markdown_content.append(f"{comment.body}\n")

    # Add replies to this comment
    if comment.replies:
      for j, reply in enumerate(comment.replies):
        markdown_content.append(f"### **Reply {j+1}**, **@{reply.author}**   **at**: {reply.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n")
        markdown_content.append(f"{reply.body}\n")

    # Add separator between comments
    markdown_content.append("---\n")

  # Write the consolidated markdown file
  full_markdown_text = "\n".join(markdown_content)
  markdown_path.write_text(full_markdown_text, encoding='utf-8')

  print(f"Created file: {markdown_path}")

def output_commit_markdown(commitQueryResult: CommitQueryResult, output_directory: pathlib.Path):
  """
  Convert commit data to a markdown file named after commit SHA.

  Args:
    commitQueryResult (CommitQueryResult): The commit data
    output_directory (pathlib.Path): Directory to save the markdown file
  """
  output_directory.mkdir(parents=True, exist_ok=True)
  markdown_path = output_directory.joinpath(f"commit_{commitQueryResult.oid}.md")

  markdown_content = []
  markdown_content.append(f"# Commit: {commitQueryResult.oid}\n")
  markdown_content.append(f"**Author**: @{commitQueryResult.author}   **Committed at**: {commitQueryResult.committedDate.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n")
  markdown_content.append(f"{commitQueryResult.message}\n")
  markdown_content.append("---\n")

  full_markdown_text = "\n".join(markdown_content)
  markdown_path.write_text(full_markdown_text, encoding='utf-8')
  print(f"Created file: {markdown_path}")

def output_commits_to_single_markdown(commitsQueryResult: List[CommitQueryResult], output_directory: pathlib.Path, branch: str):
  """
  Convert a list of commit data to a single markdown file containing all commits.

  Args:
    commitsQueryResult (List[CommitQueryResult]): List of commit data
    output_directory (pathlib.Path): Directory to save the markdown file
    branch (str): Branch name for filename
  """
  output_directory.mkdir(parents=True, exist_ok=True)
  markdown_path = output_directory.joinpath(f"commits_{branch}.md")

  markdown_content = []
  markdown_content.append(f"# Commits on branch: {branch}\n")
  markdown_content.append("---\n")

  # Sort commits by committedDate in descending order (latest to earliest)
  commitsQueryResult.sort(key=lambda commit: commit.committedDate, reverse=True)

  commit_counter = len(commitsQueryResult) # Initialize commit_counter to the total number of commits
  for commitQueryResult in commitsQueryResult:
    markdown_content.append(f"## Commit {commit_counter:03}: {commitQueryResult.oid}\n") # Added commit counter with 3 digits format
    markdown_content.append(f"**Author**: @{commitQueryResult.author}   **Committed at**: {commitQueryResult.committedDate.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n")
    markdown_content.append(f"{commitQueryResult.message}\n")
    markdown_content.append("---\n")
    commit_counter -= 1 # Decrement commit_counter

  full_markdown_text = "\n".join(markdown_content)
  markdown_path.write_text(full_markdown_text, encoding='utf-8')
  print(f"Created file: {markdown_path}")

async def main():
  parser = argparse.ArgumentParser(description="Fetch and dump GitHub discussions or pullRequests or issues or commits data")
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

    # Split the path to extract components
    path_parts = parsed_url.path.strip("/").split("/")
    if len(path_parts) < 2:
      print(f"\nInvalid GitHub repository URL `--url`: {url}\n")
      parser.print_help()
      sys.exit(1)

    owner = path_parts[0]
    repo = path_parts[1]

    # Determine the type, number, or branch if applicable
    dumptype = None
    number = None
    branch = None
    commit_sha = None
    if len(path_parts) > 2:
      if path_parts[2] == "issues":
        dumptype = "issue"
      elif path_parts[2] == "pull":
        dumptype = "pullRequest"
      elif path_parts[2] == "discussions":
        dumptype = "discussion"
      elif path_parts[2] == "commits":
        dumptype = "commits"  # Extract branch name, default to main if not specified
        if len(path_parts) > 3:
          branch = path_parts[3]
        else:
          branch = "main" # default branch name if not specified in URL for commits
      elif path_parts[2] == "commit":
        dumptype = "commit" # Extract commit SHA
        if len(path_parts) > 3:
          commit_sha = path_parts[3]

      # Extract the number or branch or commit SHA from the fourth component (if it exists)
      if len(path_parts) > 3 and dumptype in ["issue", "pullRequest", "discussion"] and path_parts[3].isdigit():
        number = int(path_parts[3])  # Treat as a number


    return owner, repo, dumptype, number, branch, commit_sha

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
  parser.add_argument("--url", help="GitHub Repository URL. Automatically extracts `owner`, `repo`, `dumptype`, and either `numbers` (for discussions, issues, or pull requests) or `branch` (for commits) or `sha` (for commit) based on the provided URL")
  parser.add_argument("--owner", help="GitHub Repository Owner, required unless `--url` is provided")
  parser.add_argument("--repo", help="GitHub Repository Name, required unless `--url` is provided")
  parser.add_argument("-dt", "--dumptype", help="Enter discussion or pullRequest or issue or commits or commit, default discussion", default="discussion")
  parser.add_argument("-n", "--numbers", nargs='+', type=parse_range, help="GitHub Discussion or PullRequest or Issue Numbers (space-separated, supports ranges like '1000-1200')")
  parser.add_argument("--branch", help="Git branch is required when `dumptype` is set to `commits` or provided through `--url`")
  parser.add_argument("--sha", help="Git commit sha is required when `dumptype` is set to `commit` or provided through `--url`")
  parser.add_argument("-o", "--output-dir", help="Output directory for markdown files, default docs", default="docs")
  parser.add_argument("--api", help="GitHub GraphQL endpoint, default https://api.github.com/graphql", default="https://api.github.com/graphql")
  args = parser.parse_args()

  if not args.token:
    # Attempt to obtain a GitHub authentication token using the gh auth login command from the GitHub CLI
    args.token = get_gh_token()

  if args.url:
    args.owner, args.repo, dumptype, number, args.branch, args.sha = parse_github_url(args.url)
    if dumptype:
      args.dumptype = dumptype
      if number:
        if not args.numbers:
          args.numbers = []
        args.numbers.append([number])  # Append the extracted number as a list for consistency


  if not args.owner or not args.repo:
    print("\nError: `--owner` and `--repo` are required options, or you can specify `--url` to automatically retrieve the owner and repo.\n")
    parser.print_help()
    sys.exit(1)

  if args.dumptype == 'commits' and not args.branch:
    print("\nError: `--branch` is required when `dumptype` is set to `commits`.\n")
    parser.print_help()
    sys.exit(1)

  if args.dumptype == 'commit' and not args.sha:
    print("\nError: `--sha` is required when `dumptype` is set to `commit`.\n")
    parser.print_help()
    sys.exit(1)

  # Convert discussion numbers to flatten list
  numbers = []
  if args.numbers:
    numbers = [item for sublist in args.numbers for item in sublist]
  # Convert output directory to Path object
  output_dir = pathlib.Path(args.output_dir) / args.repo

  args.dumptype = args.dumptype

  async with aiohttp.ClientSession(trust_env=True) as session:
    # Process each discussion number
    fetch_processed = 0
    fetch_failed = 0
    if args.dumptype in ["discussion", "pullRequest", "issue"]:
      for number in numbers:
        try:
          # Fetch discussion data
          query_result = await fetch_github_data(
            session,
            args.api,
            args.token,
            args.owner,
            args.repo,
            args.dumptype,
            number,
          )

          # Output as markdown file if discussion exists
          if query_result:
            output_markdown(query_result, output_dir, number)
            fetch_processed += 1
          else:
            fetch_failed += 1
        except Exception as e:
          print(traceback.format_exc())
          print(f"Error processing {args.dumptype} {number:03}: {e}")
          fetch_failed += 1
    elif args.dumptype == "commits":
      try:
        commits_query_result = await fetch_github_data(
          session,
          args.api,
          args.token,
          args.owner,
          args.repo,
          args.dumptype,
          branch=args.branch,
        )
        if commits_query_result:
          output_commits_to_single_markdown(commits_query_result, output_dir, args.branch) # call the new function to output all commits to a single file
          fetch_processed = len(commits_query_result) # processed count is the number of commits
        else:
          fetch_failed += 1
      except Exception as e:
        print(traceback.format_exc())
        print(f"Error processing {args.dumptype} on branch {args.branch}: {e}")
        fetch_failed += 1
    elif args.dumptype == "commit":
      try:
        commit_query_result = await fetch_github_data(
          session,
          args.api,
          args.token,
          args.owner,
          args.repo,
          args.dumptype,
          sha=args.sha,
        )
        if commit_query_result: # commit_query_result is a single CommitQueryResult
          output_commit_markdown(commit_query_result, output_dir)
          fetch_processed += 1
        else:
          fetch_failed += 1
      except Exception as e:
        print(traceback.format_exc())
        print(f"Error processing {args.dumptype} with sha {args.sha}: {e}")
        fetch_failed += 1

    # Print summary
    print(f"\nProcessing complete.")
    print(f"{args.dumptype} processed successfully: {fetch_processed}")
    print(f"{args.dumptype} failed: {fetch_failed}")

if __name__ == "__main__":
  asyncio.run(main())