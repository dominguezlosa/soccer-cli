import click
import os
import requests
import sys
import json
import time

from soccer import leagueids
from soccer import leaguenameslive
from soccer import leaguekeys
from soccer.exceptions import IncorrectParametersException, APIErrorException
from soccer.writers import get_writer


BASE_URL = 'http://api.football-data.org/v1/'
LIVE_URL = 'http://soccer-cli.appspot.com/'
LIVE_LEAGUES_URL = 'http://soccer-cli.appspot.com/'
LEAGUE_IDS = leagueids.LEAGUE_IDS
LEAGUE_NAMES = leaguenameslive.LEAGUE_NAMES
LEAGUE_KEYS = leaguekeys.LEAGUE_KEYS


def load_json(file):
    """Load JSON file at app start"""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, file)) as jfile:
        data = json.load(jfile)
    return data


TEAM_DATA = load_json("teams.json")["teams"]
TEAM_NAMES = {team["code"]: team["id"] for team in TEAM_DATA}
LEAGUE_DATA = load_json("leagues.json")["leagues"]


def get_input_key():
    """Input API key and validate"""
    click.secho("No API key found!", fg="yellow", bold=True)
    click.secho("Please visit {0} and get an API token.".format(BASE_URL),
                fg="yellow", bold=True)
    while True:
        confkey = click.prompt(click.style("Enter API key",
                                           fg="yellow", bold=True))
        if len(confkey) == 32:  # 32 chars
            try:
                int(confkey, 16)  # hexadecimal
            except ValueError:
                click.secho("Invalid API key", fg="red", bold=True)
            else:
                break
        else:
            click.secho("Invalid API key", fg="red", bold=True)
    return confkey


def load_config_key():
    """Load API key from config file, write if needed"""
    global api_token
    try:
        api_token = os.environ['SOCCER_CLI_API_TOKEN']
    except KeyError:
        home = os.path.expanduser("~")
        config = os.path.join(home, ".soccer-cli.ini")
        if not os.path.exists(config):
            with open(config, "w") as cfile:
                key = get_input_key()
                cfile.write(key)
        else:
            with open(config, "r") as cfile:
                key = cfile.read()
        if key:
            api_token = key
        else:
            os.remove(config)  # remove 0-byte file
            click.secho('No API Token detected. '
                        'Please visit {0} and get an API Token, '
                        'which will be used by Soccer CLI '
                        'to get access to the data.'
                        .format(BASE_URL), fg="red", bold=True)
            sys.exit(1)
    return api_token


def _get(url):
    """Handles api.football-data.org requests"""
    req = requests.get(BASE_URL+url, headers=headers)

    if req.status_code == requests.codes.ok:
        return req

    if req.status_code == requests.codes.bad:
        raise APIErrorException('Invalid request. Check parameters.')

    if req.status_code == requests.codes.forbidden:
        raise APIErrorException('This resource is restricted')

    if req.status_code == requests.codes.not_found:
        raise APIErrorException('This resource does not exist. Check parameters')

    if req.status_codes == requests.codes.too_many_requests:
        raise APIErrorException('You have exceeded your allowed requests per minute/day')


def get_live_scores(writer, use_12_hour_format, refresh):
    """Gets the live scores"""
    req = requests.get(LIVE_URL)
    if req.status_code == requests.codes.ok:
        scores = req.json()
        if len(scores["games"]) == 0:
            click.secho("No live action currently", fg="red", bold=True)
            return
        for game in scores["games"]:
            if game['league'] in LEAGUE_KEYS:
                game['league'] = LEAGUE_KEYS[game['league']]
        writer.live_scores(scores, use_12_hour_format)
        if refresh > 0:
            click.echo()
            click.secho("-------- Next refresh in ", fg="yellow", nl = False)
            click.secho("{0} seconds".format(refresh), fg="white", bold = True, nl = False)
            click.secho(" --------",fg="yellow");
            click.echo()
            click.echo()
            time.sleep(refresh)
            get_live_scores(writer, use_12_hour_format, refresh)
    else:
        click.secho("There was problem getting live scores", fg="red", bold=True)
        
        
def get_live_league(writer, use_12_hour_format, league, refresh):
    """Gets the live scores for a league"""
    req = requests.get(LIVE_LEAGUES_URL)
    if req.status_code == requests.codes.ok:
        scores = req.json()
        if len(scores["games"]) == 0:
            click.secho("No live action currently", fg="red", bold=True)
            return
        filtered_scores = {}
        filtered_scores["games"] = []
        for game in scores["games"]:
            if game['league'] == LEAGUE_NAMES[league]:
                game['league'] = league
                filtered_scores["games"].append(game)
        
        if len(filtered_scores["games"]) == 0:
            click.secho("No live action currently for {league}.".format(league=league), fg="red", bold=True)
            return
        writer.live_scores(filtered_scores, use_12_hour_format)
        if refresh > 0:
            click.echo()
            click.secho("-------- Next refresh in ", fg="yellow", nl = False)
            click.secho("{0} seconds".format(refresh), fg="white", bold = True, nl = False)
            click.secho(" --------",fg="yellow");
            click.echo()
            click.echo()
            time.sleep(refresh)
            get_live_league(writer, use_12_hour_format, league, refresh)
    else:
        click.secho("There was problem getting live scores", fg="red", bold=True)


def get_team_scores(team, time, writer, show_upcoming, use_12_hour_format):
    """Queries the API and gets the particular team scores"""
    team_id = TEAM_NAMES.get(team, None)
    time_frame = 'n' if show_upcoming else 'p'
    if team_id:
        try:
            req = _get('teams/{team_id}/fixtures?timeFrame={time_frame}{time}'.format(
                        team_id=team_id, time_frame=time_frame, time=time))
            team_scores = req.json()
            if len(team_scores["fixtures"]) == 0:
                word = 'next' if show_upcoming else 'past'
                click.secho("No action during {word} {time} days. Change the time "
                            "parameter to get more fixtures.".format(word=word, time=time),
                            fg="red", bold=True)
            else:
                writer.team_scores(team_scores, time, show_upcoming, use_12_hour_format)
        except APIErrorException as e:
            click.secho(e.args[0],
                        fg="red", bold=True)
    else:
        click.secho("Team code is not correct.",
                    fg="red", bold=True)

def get_matchday_standings(league, writer, extended, matchday):
    """Queries the API and gets the standings for a particular matchday for a league"""
    league_id = LEAGUE_IDS[league]
    try:
        req = _get('competitions/{id}'.format(
                    id=league_id))
        competition = req.json()
        if competition["currentMatchday"] < matchday:
            click.secho("The current matchday for this league is {matchday}, "
                        "introduce a value that is less than or equal to it.".format(matchday=competition["currentMatchday"]),
                    fg="red", bold=True)
            return
        
        req = _get('competitions/{id}/leagueTable/?matchday={matchday}'.format(
                    id=league_id, matchday=matchday))
        if extended:
            writer.standings_extended(req.json(), league)
        else:
            writer.standings(req.json(), league)
    except APIErrorException:
        # Click handles incorrect League codes so this will only come up
        # if that league does not have standings available. ie. Champions League
        click.secho("No standings availble for {league}.".format(league=league),
                    fg="red", bold=True)


def get_standings(league, writer, extended):
    """Queries the API and gets the standings for a particular league"""
    league_id = LEAGUE_IDS[league]
    try:
        req = _get('competitions/{id}/leagueTable'.format(
                    id=league_id))
        if extended:
            writer.standings_extended(req.json(), league)
        else:
            writer.standings(req.json(), league)
    except APIErrorException:
        # Click handles incorrect League codes so this will only come up
        # if that league does not have standings available. ie. Champions League
        click.secho("No standings availble for {league}.".format(league=league),
                    fg="red", bold=True)


def get_league_scores(league, time, writer, show_upcoming, use_12_hour_format):
    """
    Queries the API and fetches the scores for fixtures
    based upon the league and time parameter
    """
    time_frame = 'n' if show_upcoming else 'p'
    if league:
        try:
            league_id = LEAGUE_IDS[league]
            req = _get('competitions/{id}/fixtures?timeFrame={time_frame}{time}'.format(
                 id=league_id, time_frame=time_frame, time=str(time)))
            fixtures_results = req.json()
            # no fixtures in the selected time frame. display a help message and return
            if len(fixtures_results["fixtures"]) == 0:
                word = 'next' if show_upcoming else 'past'
                click.secho("No {league} matches in the {word} {time} days."
                            .format(league=league, word=word, time=time),
                            fg="red", bold=True)
                return
            writer.league_scores(fixtures_results, time, show_upcoming, use_12_hour_format)
        except APIErrorException:
            click.secho("No data for the given league.", fg="red", bold=True)
    else:
        # When no league specified. Print all available in time frame.
        try:
            req = _get('fixtures?timeFrame={time_frame}{time}'.format(
                 time_frame=time_frame, time=str(time)))
            fixtures_results = req.json()
            writer.league_scores(fixtures_results, time, show_upcoming, use_12_hour_format)
        except APIErrorException:
            click.secho("No data available.", fg="red", bold=True)


def get_team_players(team, writer):
    """
    Queries the API and fetches the players
    for a particular team
    """
    team_id = TEAM_NAMES.get(team, None)
    try:
        req = _get('teams/{team_id}/players'.format(
                   team_id=team_id))
        team_players = req.json()
        if int(team_players["count"]) == 0:
            click.secho("No players found for this team", fg="red", bold=True)
        else:
            writer.team_players(team_players)
    except APIErrorException:
        click.secho("No data for the team. Please check the team code.",
                    fg="red", bold=True)


def map_team_id(code):
    """Take in team ID, read JSON file to map ID to name"""
    for team in TEAM_DATA:
        if team["code"] == code:
            click.secho(team["name"], fg="green")
            break
    else:
        click.secho("No team found for this code", fg="red", bold=True)


def list_team_codes():
    """List team names in alphabetical order of team ID, per league."""
    # Sort teams by league, then alphabetical by code
    cleanlist = sorted(TEAM_DATA, key=lambda k: (k["league"]["name"], k["code"]))
    # Get league names
    leaguenames = sorted(list(set([team["league"]["name"] for team in cleanlist])))
    for league in leaguenames:
        teams = [team for team in cleanlist if team["league"]["name"] == league]
        click.secho(league, fg="green", bold=True)
        for team in teams:
            if team["code"] != "null":
                click.secho(u"{0}: {1}".format(team["code"], team["name"]), fg="yellow")
        click.secho("")
        
def list_league_codes():
    """List supported league names."""
    for league in LEAGUE_DATA:
        click.secho(u"{0}: {1}".format(league["code"], league["name"]), fg="yellow")


@click.command()
@click.option('--apikey', default=load_config_key,
              help="API key to use.")
@click.option('--list', 'listcodes', is_flag=True,
              help="List all valid team code/team name pairs.")
@click.option('--leagues', 'listleagues', is_flag=True,
              help="Shows all the supported leagues.")
@click.option('--live', is_flag=True,
              help="Shows live scores from various leagues.")
@click.option('--refresh', default=-1,
              help="Time in seconds for the live refresh.")
@click.option('--use12hour', is_flag=True, default=False,
              help="Displays the time using 12 hour format instead of 24 (default).")
@click.option('--standings', is_flag=True,
              help="Standings for a particular league.")
@click.option('--extended', is_flag=True, default=False,
              help="Displays extra info when used with --standings command."
              "GA = Goals against."
              "GF = Goals for."
              "GD = Goals difference."
              "HGF = Home Goals For."
              "HW = Home Wins."
              "HD = Home Draws."
              "HL = Home Losses."
              "AGF = Away Goals Difference."
              "AGA = Away Goals Away."
              "AW = Away Wins."
              "AD = Away Draws."
              "AL = Away Losses.")
@click.option('--matchday', default=-1,
              help="The matchday of the league for which you want to see the standings.")              
@click.option('--league', '-league', type=click.Choice(LEAGUE_IDS.keys()),
              help=("Select fixtures from a particular league."))
@click.option('--players', is_flag=True,
              help="Shows players for a particular team.")
@click.option('--team', type=click.Choice(TEAM_NAMES.keys()),
              help=("Choose a particular team's fixtures."))
@click.option('--lookup', is_flag=True,
              help="Get full team name from team code when used with --team command.")
@click.option('--time', default=6,
              help="The number of days in the past for which you want to see the scores.")
@click.option('--upcoming', is_flag=True, default=False,
              help="Displays upcoming games when used with --time command.")
@click.option('--stdout', 'output_format', flag_value='stdout', default=True,
              help="Print to stdout.")
@click.option('--csv', 'output_format', flag_value='csv',
              help='Output in CSV format.')
@click.option('--json', 'output_format', flag_value='json',
              help='Output in JSON format.')
@click.option('-o', '--output-file', default=None,
              help="Save output to a file (only if csv or json option is provided).")
def main(league, time, standings, extended, matchday, team, live, refresh, use12hour,
        players, output_format, output_file, upcoming, lookup, listcodes, listleagues, apikey):
    """
    A CLI for live and past football scores from various football leagues.

    League codes:

    \b
    - CL: Champions League
    - EPL: Premier League
    - EL1: League One
    - FL: Ligue 1
    - FL2: Ligue 2
    - BL: Bundesliga
    - BL2: 2. Bundesliga
    - BL3: 3. Liga
    - SA: Serie A
    - DED: Eredivisie
    - PPL: Primeira Liga
    - LLIGA: La Liga
    - SD: Segunda Division
    """
    global headers
    headers = {'X-Auth-Token': apikey}

    try:
        if output_format == 'stdout' and output_file:
            raise IncorrectParametersException('Printing output to stdout and '
                                               'saving to a file are mutually exclusive')
        writer = get_writer(output_format, output_file)

        if listcodes:
            list_team_codes()
            return
        
        if listleagues:
            list_league_codes()
            return

        if live:
            if league:
                get_live_league(writer, use12hour, league, refresh)
            else:
                get_live_scores(writer, use12hour, refresh)
            return

        if standings:
            if not league:
                raise IncorrectParametersException('Please specify a league. '
                                                   'Example --standings --league=EPL')
            if matchday > 0:
                get_matchday_standings(league, writer, extended, matchday)
            else:    
                get_standings(league, writer, extended)
            return
        
        if time < 1:
            raise IncorrectParametersException('Please specify a time value greater than 0.')

        if team:
            if lookup:
                map_team_id(team)
                return
            if players:
                get_team_players(team, writer)
                return
            else:
                get_team_scores(team, time, writer, upcoming, use12hour)
                return

        get_league_scores(league, time, writer, upcoming, use12hour)
    except IncorrectParametersException as e:
        click.secho(e.message, fg="red", bold=True)

if __name__ == '__main__':
    main()
