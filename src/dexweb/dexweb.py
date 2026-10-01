import os, json, shutil, subprocess, datetime

#Web services for dex
class Dexweb:
    def __init__(self):
        root = os.getcwd()
        self.config = {}
        if os.path.exists(os.path.join(root, 'config.json')):
            with open(os.path.join(root, 'config.json'), 'r') as file:
                self.config = json.loads(file.read())
        self.dexname = self.config.get('dexname', 'Sample')
        self.site_folder_path = os.path.join(root, 'gen')

    #publish gen/ in config's publish object, without publish, do nothing
    def publish(self):
        p = self.config.get('publish')
        if not isinstance(p, dict):
            print('no publish obj, dex not published')
            return False
        if not os.path.isdir(self.site_folder_path) or not os.listdir(self.site_folder_path):
            print('gen/ is empty, build dex first')
            return False
        method = p.get('method', 'git')
        if method == 'git':
            return self.publish_git(p)
        if method == 'folder':
            return self.publish_folder(p)
        print('unknown publish method "' + str(method) + '" in config')
        return False

    # copy gen/ into path folder, never delete files
    def publish_folder(self, p):
        if not p.get('path'):
            print('path needed for folder publishing method')
            return False
        target = os.path.normpath(os.path.join(os.getcwd(), p['path']))
        os.makedirs(target, exist_ok=True)
        shutil.copytree(self.site_folder_path, target, dirs_exist_ok=True)
        print('dex published to ' + target)
        return True

    def run_git(self, repo, *args):
        try:
            r = subprocess.run(['git', '-C', repo] + list(args), capture_output=True, text=True)
        except FileNotFoundError:
            return 127, 'git not installed'
        return r.returncode, (r.stdout + r.stderr).strip()

    # push gen/ to git repository root
    # credentials are git's own (SSH key or credential helper)
    # no credentials in config.json
    def publish_git(self, p):
        root = os.getcwd()
        dest = p.get('dest')
        remote = p.get('remote', 'origin')
        managed = bool(dest) and not os.path.isdir(os.path.join(root, dest))
        if managed:
            # tdest is repository address, keep copy in .publish/
            work = os.path.join(root, '.publish')
            if not os.path.isdir(os.path.join(work, '.git')):
                code, out = self.run_git(root, 'clone', dest, work)
                if code != 0:
                    print('publish: could not clone ' + dest + '\n' + out)
                    return False
        else:
            # dest local or absent:
            work = os.path.join(root, dest or '.')
        code, top = self.run_git(work, 'rev-parse', '--show-toplevel')
        if code != 0 or os.path.realpath(top) != os.path.realpath(work):
            # never use a repository found in a parent folder: the folder itself must be the repository
            print('publish: ' + os.path.normpath(work) + ' is not a git repository. Set "dest" in config.json "publish" to a repository address or a repository folder')
            return False
        branch = p.get('branch')
        if not branch:
            code, branch = self.run_git(top, 'rev-parse', '--abbrev-ref', 'HEAD')
            if code != 0 or branch == 'HEAD':
                print('publish: set "branch" in config.json "publish"')
                return False
        if managed:
            # the working copy is dexweb's own: bring it up to date before copying the site in
            self.run_git(top, 'fetch', remote)
            code, _ = self.run_git(top, 'rev-parse', '--verify', '--quiet', remote + '/' + branch)
            if code == 0:
                code, out = self.run_git(top, 'merge', '--ff-only', remote + '/' + branch)
                if code != 0:
                    print('publish: could not update .publish/ from ' + remote + '/' + branch + '\n' + out)
                    return False
        # copy the site into the repository root (or "site_path", e.g. "docs"). Never deletes files there.
        site = os.path.normpath(os.path.join(top, p.get('site_path', '.')))
        os.makedirs(site, exist_ok=True)
        shutil.copytree(self.site_folder_path, site, dirs_exist_ok=True)
        paths = [os.path.join(site, name) for name in os.listdir(self.site_folder_path)]
        code, out = self.run_git(top, 'add', '-A', '--', *paths)
        if code != 0:
            print('publish: git add failed\n' + out)
            return False
        code, _ = self.run_git(top, 'diff', '--cached', '--quiet')
        if code == 1:
            message = p.get('message', 'Publish {}').replace('{}', self.dexname)
            message += ' (' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') + ')'
            code, out = self.run_git(top, 'commit', '-m', message)
            if code != 0:
                print('publish: git commit failed\n' + out)
                return False
        else:
            print('publish: no changes to commit')
        code, out = self.run_git(top, 'push', remote, 'HEAD:' + branch)
        if code != 0:
            # usually someone (or another device) published first. Never force: get their changes, then publish again.
            print('publish: push to ' + remote + '/' + branch + ' was rejected. Run git pull, then publish again.\n' + out)
            return False
        print('dex published to ' + remote + '/' + branch)
        return True
