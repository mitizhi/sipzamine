#!/usr/bin/env python
# vim: set ts=8 sw=4 sts=4 et ai tw=79:
# sipcaparseye main (SIP Pcap Parse Eye)
# Copyright (C) 2011-2014 Walter Doekes, OSSO B.V.
from datetime import datetime

from libdata import PcapReader, VerboseTcpdumpReader
from libprotosip import SipDialogs

# Matches dialogs and times and looks for certain info (EYE).
# FIXME: rename this to: sipzamine (sip examine)
# TODO: the verbosereader should add CR's back.. now that we have the
# libpcapreader it should be deprecated too..


class epochtime_without_date(object):
    """
    Magic float that ignores the date so time-only comparisons can be
    done.  Take care to ensure that in datetime comparisons, this object
    is on the LHS, so these overloaded __cmp__ operator can do its job.

    NOTE: We calculate the delta between daylight saving time in the initial
    value and the compared value ONLY ONCE.  This will produce crazy results
    around DST changes.  Also, around hour 00:00 we cannot guarantee any
    meaningful result either.  This is a quick hack that works in 95% of the
    cases.
    """
    def __init__(self, floatval):
        print >>sys.stderr, \
            ('(warning: partial date parsing is inaccurate! use only if '
             'you know understand the limitations)')
        self.floatval = floatval
        self.dstdelta = None

    def __float__(self):
        return self.floatval

    def __cmp__(self, other):
        otherval = float(other)

        if self.dstdelta is None:
            self.dstdelta = (
                (datetime.fromtimestamp(otherval) -
                 datetime.utcfromtimestamp(otherval)).seconds -
                (datetime.fromtimestamp(self.floatval) -
                 datetime.utcfromtimestamp(self.floatval)).seconds
            )

        selfval = self.floatval % 86400.0
        otherval = (otherval + self.dstdelta) % 86400.0
        return cmp(selfval, otherval)


def dateskew_filter(reader, skew):
    """
    Alter reader to shift all iterated object dates by dateskew.
    """
    for packet in reader:
        packet.datetime += skew
        yield packet


def minduration_filter(reader, min_duration):
    """
    Filter dialogs by minimum duration.
    """
    for dialog in reader:
        duration = dialog[-1].datetime - dialog[0].datetime
        if duration >= min_duration:
            yield dialog


def maxduration_filter(reader, max_duration):
    """
    Filter dialogs by maximum duration.
    """
    for dialog in reader:
        duration = dialog[-1].datetime - dialog[0].datetime
        if duration <= max_duration:
            yield dialog


def allheaders_filter(reader, header_match):
    """
    Filter dialogs by a regexp which must match all packets in the dialog.
    """
    for dialog in reader:
        for packet in dialog:
            if not packet.search(header_match):
                break
        else:
            yield dialog


def anyheader_filter(reader, header_match):
    """
    Filter dialogs by a regexp which must match any packet in the dialog.
    """
    for dialog in reader:
        for packet in dialog:
            if packet.search(header_match):
                yield dialog
                break


def print_dialog(dialog, packet_highlights=None, show_contents=False):
    packet_highlights = packet_highlights or ()  # make sure it's iterable
    if show_contents:
        data_munge = re.compile('^', re.MULTILINE)

    print '[', dialog[0].callid, ']'
    for packet in dialog:
        highlights = []
        for i, packet_highlight in enumerate(packet_highlights):
            found_here = packet.search(packet_highlight)
            if found_here:
                if len(packet_highlights) == 1:
                    arrow = '<--'
                else:
                    arrow = '<-%s-' % (chr(ord('a') + i),)
                if not found_here.groups():
                    highlights.append(arrow)
                else:
                    highlights.append('%s %s' %
                                      (arrow, found_here.groups()[0]))

        print '%s %s:%d > %s:%d %s %s %s' % (
            packet.datetime, packet.from_[0], packet.from_[1],
            packet.to[0], packet.to[1],
            packet.cseq[0], packet.method_and_status, ' '.join(highlights)
        )

        if show_contents:
            print data_munge.sub('  ', packet.data)

    print


def main(reader, packet_matches=None, packet_highlights=None,
         min_duration=None, max_duration=None, show_contents=False):
    # Filter the dialogs
    matching_dialogs = []
    for dialog in reader:
        # print_dialog(dialog, packet_highlights, show_contents=show_contents)
        matching_dialogs.append(dialog)

    # Order dialogs by begin-time and first then print them
    matching_dialogs.sort(key=lambda x: x[0].datetime)
    for dialog in matching_dialogs:
        print_dialog(dialog, packet_highlights, show_contents=show_contents)


if __name__ == '__main__':
    from time import mktime, strptime
    import re
    import sys
    try:
        import argparse
    except ImportError:
        import argparse_1_2_1 as argparse

    def my_regex(regexstring):
        try:
            return re.compile(regexstring)
        except:
            raise ValueError()

    def my_strptime(timestring):
        for style, prefix in (
                ('%Y-%m-%d %H:%M:%S', ''),
                ('%Y-%m-%d %H:%M', ''),
                ('%Y-%m-%d', ''),
                ('%Y-%m-%d %H:%M:%S', '2000-01-01 '),
                ('%Y-%m-%d %H:%M', '2000-01-01 ')):
            try:
                parsed = strptime(prefix + timestring, style)
            except ValueError:
                pass
            else:
                ret = mktime(parsed)
                if prefix:
                    ret = epochtime_without_date(ret)
                break
        else:
            raise ValueError('Invalid time format, use YYYY-MM-DD '
                             'HH:MM:SS or shortened')
        return ret

    def my_timedelta(floatstring):
        if '.' in floatstring:
            # Add enough zeroes so the int value is large enough..
            floatstring = '0%s000000' % (floatstring,)
            num = [int(floatstring.split('.', 1)[0]),       # seconds
                   int(floatstring.split('.', 1)[1][0:6])]  # milliseconds
        else:
            num = [int(floatstring),  # seconds
                   0]                 # milliseconds
        if sum(num) == 0:
            raise ValueError('Specifying a zero time breaks boolean tests')
        return datetime.timedelta(seconds=num[0], milliseconds=num[1])

    # Example: sipcaparseye -m '^INVITE' -H 'm=audio ([0-9]+)' \
    #                       -p 'host 1.2.3.4' 5060.pcap.00

    description = 'Search and examine SIP transactions/dialogs'
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument(
        'files', metavar='PCAP', nargs='+',
        help=('pcap files to parse, or - to read tcpdump -nnvs0 output '
              'from stdin'))
    parser.add_argument(
        '--pcap', '-p', metavar='filter',
        help='pcap filter expression')

    # FIXME: remark that the searches are performed on the header lines and
    # can be anchored as such
    parser.add_argument(
        '--pmatch', '-m', metavar='regex', action='append',
        type=my_regex,
        help=('any packet in dialog must match regex (can be used '
              'multiple times), e.g. ^INVITE to match calls'))
    # FIXME: we may need to tweak the --option-name here too, and the
    # description
    parser.add_argument(
        '--amatch', '-M', metavar='regex', action='append',
        type=my_regex,
        help='all packets in dialog must match regex (can be used '
             'multiple times), e.g. ^(SIP/2.0|INVITE|BYE) to match calls '
             'without an ACK')
    parser.add_argument(
        '--highlight', '-H', metavar='regex', action='append',
        type=my_regex,
        help=('highlight first matchgroup in packets (multiple '
              'highlights are identified by letters a..z)'))

    parser.add_argument(
        '--dateskew', metavar='seconds', default=0, type=int,
        help=('offset added to all dates, can be negative (use when pcap '
              'clock was off)'))

    parser.add_argument(
        '--mindate', metavar='date', type=my_strptime,
        help='packets must be younger than specified date')
    parser.add_argument(
        '--maxdate', metavar='date', type=my_strptime,
        help='packets must be older than specified date')

    parser.add_argument(
        '--mindur', metavar='seconds', type=my_timedelta,
        help='dialogs/transactions must be shorter than duration')
    parser.add_argument(
        '--maxdur', metavar='seconds', type=my_timedelta,
        help='dialogs/transactions must be longer than duration')

    parser.add_argument(
        '--contents', action='store_true', default=False,
        help='show complete packet contents')

    # We don't do parse_args(), but we do parse_known_args().
    # If we did parse_args(), we'd choke on:
    #   file1 file2 --someoption file3 file4
    # with this error:
    #   unrecognized arguments: file3 file4
    # Using parse_known_args() we get the unknown arguments as extra files,
    # but we'll have to add code to check for unknown options.
    args, extra = parser.parse_known_args()

    unrecognised = []
    for i, value in enumerate(extra):
        if value == '--':
            extra.pop(i)
            break
        elif value and value[0] == '-':
            unrecognised.append(value)
    if unrecognised:
        parser.error('unrecognized arguments: %s' % (' '.join(unrecognised),))

    args.files.extend(extra)

    # Update the search dates according to the date skew
    if args.dateskew:
        args.dateskew = datetime.timedelta(seconds=args.dateskew)
        if args.mindate:
            args.mindate += args.dateskew
        if args.maxdate:
            args.maxdate += args.dateskew

    # Create a packet reader
    if len(args.files) == 1 and args.files[0] == '-':
        if args.pcap:
            parser.error('Cannot use pcap filter with stdin mode')
        reader = VerboseTcpdumpReader(sys.stdin, min_date=args.mindate,
                                      max_date=args.maxdate)
    else:
        reader = PcapReader(args.files, pcap_filter=args.pcap,
                            min_date=args.mindate, max_date=args.maxdate)

    # Optionally add a date skew on the packets
    if args.dateskew:
        reader = dateskew_filter(reader, skew=args.dateskew)

    # Convert the packets into SIP dialogs
    reader = SipDialogs(reader)

    # Optionally add duration and search filters (try to put the light weight
    # ones first)
    if args.mindur:
        reader = minduration_filter(reader, min_duration=args.mindur)
    if args.maxdur:
        reader = maxduration_filter(reader, max_duration=args.maxdur)
    if args.amatch:
        for amatch in args.amatch:
            reader = allheaders_filter(reader, header_match=amatch)
    if args.pmatch:
        for pmatch in args.pmatch:
            reader = anyheader_filter(reader, header_match=pmatch)

    # Call main with our pimped reader
    main(reader, packet_highlights=args.highlight, show_contents=args.contents)

    # Example usage:
    #
    # $ sipcaparseye -m 'sip:\+315' -H '^BYE' --pcap 'host banana' \
    #                stored.pcap
    # (or)
    # $ /usr/sbin/tcpdump -nnvs0 -r stored.pcap host banana |
    #       sipcaparseye -m 'sip:\+315' -H '^BYE' -
    #
    # Example output:
    #
    # [ 179978155f707e3622c0886752336210@22.22.22.22 ]
    # 2011-11-23 22:27:20.746782 apple:5060 > banana:5060 102 INVITE
    # 2011-11-23 22:27:20.747508 banana:5060 > apple:5060 102 INVITE(100)
    # 2011-11-23 22:27:20.783424 banana:5060 > apple:5060 102 INVITE(200)
    # 2011-11-23 22:27:20.783956 apple:5060 > banana:5060 102 ACK
    # 2011-11-23 22:27:41.665581 apple:5060 > banana:5060 103 BYE <--
    # 2011-11-23 22:27:41.665721 banana:5060 > apple:5060 103 BYE(200)
    #
    # [ 64e9278b4cdabb7c02f8c54f301937e7@apple ]
    # 2011-11-23 22:28:16.875647 apple:5060 > banana:5060 102 INVITE
    # 2011-11-23 22:28:16.876433 banana:5060 > apple:5060 102 INVITE(100)
    # 2011-11-23 22:28:16.901755 banana:5060 > apple:5060 102 INVITE(200)
    # 2011-11-23 22:28:16.902327 apple:5060 > banana:5060 102 ACK
    # 2011-11-23 22:28:24.363193 apple:5060 > banana:5060 103 BYE <--
    # 2011-11-23 22:28:24.363352 banana:5060 > apple:5060 103 BYE(200)