"""CLI accepts only named synthetic fixtures; never echo rejected arguments."""
import argparse
import json
import sys

from . import core, drive, fixtures


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise core.ContextError('INVALID_COMMAND')


def main(argv=None):
    try:
        parser = Parser(description='Offline synthetic-only shared context. No live X/Drive connection.')
        parser.add_argument('mode', choices=('preview', 'generate', 'verify', 'publish'))
        parser.add_argument('--synthetic-fixtures', choices=fixtures.NAMES)
        parser.add_argument('--output')
        parser.add_argument('--sandbox')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--apply', action='store_true')
        args = parser.parse_args(argv)
        if args.mode == 'publish':
            if not args.synthetic_fixtures or not args.sandbox or args.output or args.dry_run == args.apply:
                raise core.ContextError('INVALID_COMMAND')
            result = drive.disconnected_plan(core.load_fixture(args.synthetic_fixtures), args.sandbox)
            if args.apply:
                raise core.ContextError('DRIVE_AUTH_UNAVAILABLE')
        else:
            if not args.output or args.sandbox or args.dry_run or args.apply:
                raise core.ContextError('INVALID_COMMAND')
            if args.mode == 'verify':
                if args.synthetic_fixtures:
                    raise core.ContextError('INVALID_COMMAND')
                result = dict(status='VERIFIED', records=len(core.verify(args.output)))
            else:
                if not args.synthetic_fixtures:
                    raise core.ContextError('INVALID_COMMAND')
                records = core.load_fixture(args.synthetic_fixtures)
                counts = core.preview(records, args.output) if args.mode == 'preview' else core.generate(records, args.output)
                result = dict(status='PREVIEW' if args.mode == 'preview' else 'GENERATED', **counts)
        print(json.dumps(dict(provider_requests_attempted=0, **result), sort_keys=True))
        return 0
    except core.ContextError as error:
        print(json.dumps(dict(error=str(error), provider_requests_attempted=0)), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
