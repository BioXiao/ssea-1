'''
Created on Oct 29, 2013

@author: mkiyer
'''
import sys
import os
import argparse
import gzip
import json
import logging

# set matplotlib backend
import matplotlib
matplotlib.use('Agg')

# third-party packages
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib import figure
from jinja2 import Environment, PackageLoader

# local imports
from ssea import __version__, __date__, __updated__
from ssea.base import timestamp, Result

# setup path to web files
import ssea
SRC_WEB_PATH = os.path.join(ssea.__path__[0], 'web')

# setup html template environment
env = Environment(loader=PackageLoader("ssea", "templates"),
                  extensions=["jinja2.ext.loopcontrols"])

# matplotlib static figure for plotting
global_fig = plt.figure(0)

class ReportConfig(object):
    def __init__(self):
        self.num_processes = 1
        self.input_dir = None
        self.output_dir = None
        self.thresholds = []
        self.plot_conf_int = True
        self.conf_int = 0.95
        self.create_html = True
        self.create_plots = True

    def get_argument_parser(self, parser=None):
        if parser is None:
            parser = argparse.ArgumentParser()
        grp = parser.add_argument_group("SSEA Report Options")
        grp.add_argument('-p', '--num-processes', dest='num_processes',
                         type=int, default=1,
                         help='Number of processor cores available '
                         '[default=%(default)s]')
        grp.add_argument('-o', '--output-dir', dest="output_dir", 
                         default=self.output_dir,
                         help='Output directory [default=%(default)s]')
        grp.add_argument('--no-html', dest="create_html", 
                         action="store_false", default=self.create_html,
                         help='Do not create detailed html reports')
        grp.add_argument('--no-plot', dest="create_plots", 
                         action="store_false", default=self.create_plots,
                         help='Do not create enrichment plots')
        grp.add_argument('--threshold', type=float, action="append",
                         dest="thresholds",
                         help='Significance thresholds for generating '
                         'detailed reports [default=%(default)s]')
        grp.add_argument('--no-plot-conf-int', dest="plot_conf_int", 
                         action="store_false", default=self.plot_conf_int,
                         help='Do not show confidence intervals in '
                         'enrichment plot')
        grp.add_argument('--conf-int', dest="conf_int", type=float, 
                         default=self.conf_int,
                         help='Confidence interval level '
                         '[default=%(default)s]')
        grp.add_argument('input_dir')
        return parser        

    def log(self, log_func=logging.info):
        log_func("Parameters")
        log_func("----------------------------------")
        log_func("num processes:           %d" % (self.num_processes))
        log_func("input directory:         %s" % (self.input_dir))
        log_func("output directory:        %s" % (self.output_dir))
        log_func("create html report:      %s" % (self.create_html))
        log_func("create plots:            %s" % (self.create_plots))
        log_func("plot conf interval:      %s" % (self.plot_conf_int))
        log_func("conf interval:           %f" % (self.conf_int))
        log_func("thresholds:              %s" % (str(self.thresholds)))
        log_func("----------------------------------")

    def parse_args(self, parser, args):
        # process and check arguments
        self.create_html = args.create_html
        self.create_plots = args.create_plots
        self.plot_conf_int = args.plot_conf_int
        self.conf_int = args.conf_int
        self.num_processes = args.num_processes
        # setup reporting thresholds
        self.thresholds = []        
        # check input directory
        if not os.path.exists(args.input_dir):
            parser.error("input directory '%s' not found" % (args.input_dir))
        self.input_dir = args.input_dir
        # setup output directory
        if args.output_dir is None:
            self.output_dir = "Report_%s" % (timestamp())
        else:            
            self.output_dir = args.output_dir
        if os.path.exists(self.output_dir):
            parser.error("output directory '%s' already exists" % 
                         (self.output_dir))

def enrichment_plot(d, plot_conf_int=True, conf_int=0.95, fig=None):
    if fig is None:
        fig = plt.Figure()
    else:
        fig.clf()
    gs = gridspec.GridSpec(3, 1, height_ratios=[2,1,1])
    # running enrichment score
    ax0 = fig.add_subplot(gs[0])
    x = np.arange(len(d[Result.RUNNING_ES]))
    y = d[Result.RUNNING_ES]
    ax0.plot(x, y, lw=2, color='blue', label='Enrichment profile')
    ax0.axhline(y=0, color='gray')
    ax0.axvline(x=d[Result.RANK_AT_MAX], lw=1, linestyle='--', color='black')
    # confidence interval
    if plot_conf_int:
        # determine confidence interval band
        es = d[Result.ES]
        es_null_mean = d[Result.ES_NULL_MEAN]
        bins = np.array(d[Result.ES_NULL_BINS])
        bin_left_edges = bins[:-1]
        h = np.array(d[Result.ES_NULL_HIST])
        if es < 0:
            sign_inds = (bin_left_edges <= 0).nonzero()[0]
        else:
            sign_inds = (bin_left_edges >= 0).nonzero()[0]
        bins_sign = bin_left_edges[sign_inds]
        h_sign = h[sign_inds]
        h_norm = h_sign.cumsum() / float(h_sign.sum())
        left = 1 + h_norm.searchsorted((1.0 - conf_int), side='right')
        left = left.clip(0,len(h)-1)
        right = h_norm.searchsorted(conf_int, side='left')
        right = right.clip(0,len(h)-1)
        # TODO: interpolate
        es_null_low = bins_sign[left]
        es_null_hi = bins_sign[right]
        lower_bound = np.repeat(es_null_low, len(x))
        upper_bound = np.repeat(es_null_hi, len(x))
        ax0.axhline(y=es_null_mean, lw=2, color='red', ls=':')
        ax0.fill_between(x, lower_bound, upper_bound,
                         lw=0, facecolor='yellow', alpha=0.5,
                         label='%.2f CI' % (100. * conf_int))
        # here we use the where argument to only fill the region 
        # where the ES is above the confidence interval boundary
        if d[Result.ES] < 0:
            ax0.fill_between(x, y, lower_bound, where=y<lower_bound, 
                             lw=0, facecolor='blue', alpha=0.5)
        else:
            ax0.fill_between(x, upper_bound, y, where=y>upper_bound, 
                             lw=0, facecolor='blue', alpha=0.5)
    ax0.set_xlim((0,len(d[Result.RUNNING_ES])))
    ax0.grid(True)
    ax0.set_xticklabels([])
    ax0.set_ylabel('Enrichment score (ES)')
    ax0.set_title('Enrichment plot: %s' % (d[Result.SS_NAME]))
    # membership in sample set
    ax1 = fig.add_subplot(gs[1])
    ax1.vlines(d[Result.MEMBERSHIP].nonzero()[0], ymin=0, ymax=1, lw=0.5, 
               color='black', label='Hits')
    ax1.set_xlim((0,len(d[Result.RUNNING_ES])))
    ax1.set_ylim((0,1))
    ax1.set_xticks([])
    ax1.set_yticks([])
    ax1.set_xticklabels([])
    ax1.set_yticklabels([])
    ax1.set_ylabel('Set')
    # weights
    ax2 = fig.add_subplot(gs[2])
    ax2.plot(d[Result.TX_WEIGHTS_MISS], color='blue')
    ax2.plot(d[Result.TX_WEIGHTS_HIT], color='red')
    ax2.set_xlim((0,len(d[Result.RUNNING_ES])))
    ax2.set_xlabel('Samples')
    ax2.set_ylabel('Weights')
    # draw
    fig.tight_layout()
    return fig

def plot_null_distribution(d, fig=None):
    if fig is None:
        fig = plt.Figure()
    else:
        fig.clf()
    # get coords of bars    
    bins = d[Result.ES_NULL_BINS]
    left = bins[:-1]
    height = d[Result.ES_NULL_HIST]
    width = [(r-l) for l,r in zip(bins[:-1],bins[1:])]
    # make plot
    ax = fig.add_subplot(1,1,1)
    ax.bar(left, height, width)
    ax.axvline(x=d[Result.ES], linestyle='--', color='black')
    ax.set_title('Random ES distribution')
    ax.set_ylabel('P(ES)')
    ax.set_xlabel('ES (Sets with neg scores: %.0f%%)' % 
                  (d[Result.ES_NULL_PERCENT_NEG]))
    return fig

def create_detailed_report(d, config):
    '''
    Generate detailed report files including enrichment plots and 
    a tab-delimited text file showing the running ES score and rank
    of each member in the sample set

    d: dictionary containing Result fields
    config: ReportConfig object
     
    returns dict containing files written
    '''
    name = d[Result.NAME]
    ss_name = d[Result.SS_NAME]
    output_dir = config.output_dir
    if config.create_plots:
        # create enrichment plot
        enrichment_plot(d, plot_conf_int=config.plot_conf_int,
                        conf_int=config.conf_int, fig=global_fig)    
        # save plots
        eplot_png = '%s.%s.eplot.png' % (name, ss_name)
        eplot_pdf = '%s.%s.eplot.pdf' % (name, ss_name)
        global_fig.savefig(os.path.join(output_dir, eplot_png))
        global_fig.savefig(os.path.join(output_dir, eplot_pdf))
        # create null distribution plot
        plot_null_distribution(d, fig=global_fig)
        nplot_png = '%s.%s.null.png' % (name, ss_name)
        nplot_pdf = '%s.%s.null.pdf' % (name, ss_name)
        global_fig.savefig(os.path.join(output_dir, nplot_png))        
        global_fig.savefig(os.path.join(output_dir, nplot_pdf))
        d.update({'eplot_png': eplot_png,
                  'nplot_png': nplot_png})
        d.update({'eplot_pdf': eplot_pdf,
                  'nplot_pdf': nplot_pdf})
    # show details of hits
    hitd = d[Result.HIT_DETAILS]
    rows = [['sample', 'rank', 'raw_weight', 'tx_weight', 'running_es', 
             'core_enrichment']]
    rows.extend(zip(hitd['sample'],
                    hitd['rank'],
                    hitd['raw_weight'],
                    hitd['tx_weight'],
                    hitd['running_es'],
                    hitd['core_enrichment']))
    details_tsv = '%s.%s.tsv' % (name, ss_name)
    fp = open(os.path.join(output_dir, details_tsv), 'w')
    for fields in rows:
        print >>fp, '\t'.join(map(str,fields))
    fp.close()
    d['tsv'] = details_tsv
    # render to html
#     if config.create_html:
#         fields = res.get_report_fields(name, desc)
#         result_dict = dict(zip(Report.FIELDS, fields))
#         details_html = '%s.%s.html' % (name, res.sample_set.name)
#         t = env.get_template('details.html')
#         fp = open(os.path.join(details_dir, details_html), 'w')
#         print >>fp, t.render(res=result_dict, 
#                              files=d,
#                              details=details_rows)
#         fp.close()
#         d['html'] = details_html
    return d


def report(config):
    # create output dir
    if not os.path.exists(config.output_dir):
        logging.debug("Creating output dir '%s'" % (config.output_dir))
        os.makedirs(config.output_dir)
    # parse report json
    json_file = os.path.join(config.input_dir, 'results.json.gz')
    fin = gzip.open(json_file, 'rb')
    for line in fin:
        # load json document (one per line) and convert
        d = json.loads(line.strip())
        d[Result.MEMBERSHIP] = np.array(d[Result.MEMBERSHIP])
        
        # TODO: use thresholds        
        create_detailed_report(d, config)
        
        # format for tab-delimited text file            
        fields = [d[Result.NAME], 
                  d[Result.DESC], 
                  d[Result.SS_NAME], 
                  d[Result.SS_DESC], 
                  d[Result.SS_SIZE],
                  d[Result.ES], 
                  d[Result.NES], 
                  d[Result.NOMINAL_P_VALUE],
                  d[Result.FDR_Q_VALUE],
                  d[Result.FWER_P_VALUE],
                  d[Result.GLOBAL_NES],
                  d[Result.GLOBAL_FDR_Q_VALUE],
                  d[Result.RANK_AT_MAX],
                  d[Result.CORE_HITS],
                  d[Result.CORE_MISSES],
                  d[Result.NULL_HITS],
                  d[Result.NULL_MISSES]]
        print '\t'.join(map(str,fields))
        # format result as tab-delimited text
        if config.create_html:
            pass
    fin.close()

def main(argv=None):
    '''Command line options.'''    
    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    program_name = os.path.basename(sys.argv[0])
    program_version = "v%s" % __version__
    program_build_date = str(__updated__)
    program_version_message = '%s %s (%s)' % (program_name, program_version, program_build_date)
    program_shortdesc = __import__('__main__').__doc__.split("\n")[1]
    program_license = '''%s

  Created by mkiyer and yniknafs on %s.
  Copyright 2013 MCTP. All rights reserved.
  
  Licensed under the GPL
  http://www.gnu.org/licenses/gpl.html
  
  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied.

USAGE
''' % (program_shortdesc, str(__date__))

    # create instance of run configuration
    config = ReportConfig()
    # Setup argument parser
    parser = argparse.ArgumentParser(description=program_license)
    # Add command line parameters
    config.get_argument_parser(parser)
    parser.add_argument("-v", "--verbose", dest="verbose", 
                        action="store_true", default=False, 
                        help="set verbosity level [default: %(default)s]")
    parser.add_argument('-V', '--version', action='version', 
                        version=program_version_message)
    # Process arguments
    args = parser.parse_args()
    # setup logging
    if args.verbose > 0:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    # initialize configuration
    config.parse_args(parser, args)
    config.log()
    report(config)
    return 0

if __name__ == "__main__":
    sys.exit(main())


# 
# 
# class Result(object):
#     def __init__(self):
#         self.name = None
#         self.desc = None
#         self.sample_set_name = None
#         self.sample_set_desc = None        
#         self.samples = None
#         self.membership = None
#         self.weights = None
#         self.weights_miss = None
#         self.weights_hit = None
#         self.es = 0.0
#         self.nes = 0.0
#         self.es_run_ind = 0
#         self.es_run = None
#         self.pval = 1.0
#         self.qval = 1.0
#         self.fwerp = 1.0
#         self.es_null = None
# 
#     def to_json(self):
#         '''
#         get json document representation of object
#         '''
#         member_inds = (self.membership > 0).nonzero()[0]
#         sample_set_size = len(member_inds)
#         num_misses = self.membership.shape[0] - sample_set_size
#         # calculate leading edge stats
#         if self.es < 0:
#             le_num_hits = sum(i >= self.es_run_ind for i in member_inds)
#             le_num_misses = self.membership.shape[0] - self.es_run_ind
#             if self.es_run_ind == 0:
#                 le_frac_hits = 0.0
#             else:
#                 le_frac_hits = float(le_num_hits) / self.es_run_ind
#         else:
#             le_num_hits = sum(i <= self.es_run_ind for i in member_inds)
#             le_num_misses = 1 + self.es_run_ind - le_num_hits
#             if self.es_run_ind == 0:
#                 le_frac_hits = 0.0
#             else:
#                 le_frac_hits = float(le_num_hits) / (1+self.es_run_ind)
#         sample_set_frac_le = float(le_num_hits) / sample_set_size
#         null_set_frac_le = float(le_num_misses) / num_misses
#         # histogram of null distribution
#         num_bins = int(round(float(self.es_null.shape[0]) ** (1./2.)))
# 
#         #n, bins, patches = ax.hist(es_null, bins=num_bins, histtype='stepfilled')
#         ax = fig.add_subplot(1,1,1)
#         ax.hist(self.es_null, bins=num_bins, histtype='bar')
# 
#         
#         
#         # build json document
#         d = {'name': self.weight_vec.name,
#              'desc': self.weight_vec.desc,
#              'sample_set_name': self.sample_set.name,
#              'sample_set_desc': self.sample_set.desc,
#              'sample_set_size': sample_set_size,
#              'es': self.es,
#              'nes': self.nes,
#              'nominal_p_value': self.pval,
#              'fdr_q_value': self.qval,
#              'fwer_p_value': self.fwerp,
#              'global_nes': 'NA',
#              'global_fdr_q_value': 'NA',
#              'rank_at_max': self.es_run_ind,
#              'leading_edge_num_hits': le_num_hits,
#              'leading_edge_frac_hits': le_frac_hits,
#              'sample_set_frac_in_leading_edge': sample_set_frac_le,
#              'null_set_frac_in_leading_edge': null_set_frac_le}
# 
# 
#         # get detailed report
#         rows = [['index', 'sample', 'rank', 'raw_weight', 
#                  'transformed_weight', 'running_es', 'core_enrichment']]
#         for i,ind in enumerate(member_inds):
#             is_enriched = int(ind <= self.es_run_ind)
#             rows.append([i, self.samples[ind], ind+1, self.weights[ind],
#                          self.weights_hit[ind], self.es_run[ind], 
#                          is_enriched])        
# 
#         return d
#    
#     def get_details_table(self):
#         rows = [['index', 'sample', 'rank', 'raw_weight', 
#                  'transformed_weight', 'running_es', 'core_enrichment']]
#         member_inds = (self.membership > 0).nonzero()[0]
#         for i,ind in enumerate(member_inds):
#             is_enriched = int(ind <= self.es_run_ind)
#             rows.append([i, self.samples[ind], ind+1, self.weights[ind],
#                          self.weights_hit[ind], self.es_run[ind], 
#                          is_enriched])
#         return rows
# 
#     def get_report_fields(self, name, desc):
#         # calculate leading edge stats
#         member_inds = (self.membership > 0).nonzero()[0]
#         le_num_hits = sum(ind <= self.es_run_ind 
#                           for ind in member_inds)
#         le_num_misses = self.es_run_ind - le_num_hits
#         num_misses = self.membership.shape[0] - len(self.sample_set)
#         sample_set_frac_le = float(le_num_hits) / len(self.sample_set)
#         null_set_frac_le = float(le_num_misses) / num_misses
#         if self.es_run_ind == 0:
#             le_frac_hits = 0.0
#         else:
#             le_frac_hits = float(le_num_hits) / self.es_run_ind
#         # write result to text file            
#         fields = [name, desc,
#                   self.sample_set.name, self.sample_set.desc, 
#                   len(self.sample_set), self.es, self.nes, self.pval, 
#                   self.qval, self.fwerp, 'NA', 'NA',
#                   self.es_run_ind,
#                   le_num_hits, le_frac_hits, 
#                   sample_set_frac_le,
#                   null_set_frac_le, '{}']
#         return fields


# 
# 
# 
# class Report(object):
#     # header fields for report
#     FIELDS = ['name', 
#               'desc',
#               'sample_set_name',
#               'sample_set_desc',
#               'sample_set_size',
#               'es',
#               'nes',
#               'nominal_p_value',
#               'fdr_q_value',
#               'fwer_p_value',
#               'global_nes',
#               'global_fdr_q_value',
#               'rank_at_max',
#               'leading_edge_num_hits',
#               'leading_edge_frac_hits',
#               'sample_set_frac_in_leading_edge',
#               'null_set_frac_in_leading_edge',
#               'details']
#     FIELD_MAP = dict((v,k) for k,v in enumerate(FIELDS))
# 
#     @staticmethod
#     def parse(filename):
#         '''
#         parses lines of the report file produced by SSEA and 
#         generates dictionaries using the first line of the file
#         containing the header fields
#         '''
#         fileh = open(filename, 'r')
#         header_fields = fileh.next().strip().split('\t')
#         details_ind = header_fields.index('details')
#         for line in fileh:
#             fields = line.strip().split('\t')
#             fields[details_ind] = json.loads(fields[details_ind])
#             yield dict(zip(header_fields, fields))
#         fileh.close()
# 
# def create_detailed_report(name, desc, res, details_dir, config):
#     '''
#     Generate detailed report files including enrichment plots and 
#     a tab-delimited text file showing the running ES score and rank
#     of each member in the sample set
# 
#     name: string
#     desc: string
#     res: base.Result object
#     details_dir: path to write files
#     config: config.Config object
#     
#     returns dict containing files written
#     '''
#     d = {}
#     if config.create_plots:
#         # create enrichment plot
#         res.plot(plot_conf_int=config.plot_conf_int,
#                  conf_int=config.conf_int, fig=global_fig)    
#         # save plots
#         eplot_png = '%s.%s.eplot.png' % (name, res.sample_set.name)
#         eplot_pdf = '%s.%s.eplot.pdf' % (name, res.sample_set.name)
#         global_fig.savefig(os.path.join(details_dir, eplot_png))
#         global_fig.savefig(os.path.join(details_dir, eplot_pdf))
#         # create null distribution plot
#         res.plot_null_distribution(fig=global_fig)
#         nplot_png = '%s.%s.null.png' % (name, res.sample_set.name)
#         nplot_pdf = '%s.%s.null.pdf' % (name, res.sample_set.name)
#         global_fig.savefig(os.path.join(details_dir, nplot_png))        
#         global_fig.savefig(os.path.join(details_dir, nplot_pdf))
#         d.update({'eplot_png': eplot_png,
#                   'nplot_png': nplot_png})
#         d.update({'eplot_pdf': eplot_pdf,
#                   'nplot_pdf': nplot_pdf})
#     # write detailed report
#     details_rows = res.get_details_table()
#     details_tsv = '%s.%s.tsv' % (name, res.sample_set.name)
#     fp = open(os.path.join(details_dir, details_tsv), 'w')
#     for fields in details_rows:
#         print >>fp, '\t'.join(map(str,fields))
#     fp.close()
#     d['tsv'] = details_tsv
#     # render to html
#     if config.create_html:
#         fields = res.get_report_fields(name, desc)
#         result_dict = dict(zip(Report.FIELDS, fields))
#         details_html = '%s.%s.html' % (name, res.sample_set.name)
#         t = env.get_template('details.html')
#         fp = open(os.path.join(details_dir, details_html), 'w')
#         print >>fp, t.render(res=result_dict, 
#                              files=d,
#                              details=details_rows)
#         fp.close()
#         d['html'] = details_html
#     return d
# 
# 
# def create_html_report(filename, rel_details_dir, config):
#     def parse_report_as_dicts(filename):
#         '''
#         parses lines of the out.txt report file produced by SSEA and 
#         generates dictionaries using the first line of the file
#         containing the header fields
#         '''
#         fileh = open(filename, 'r')
#         header_fields = fileh.next().strip().split('\t')
#         details_ind = header_fields.index('details')
#         for line in fileh:
#             fields = line.strip().split('\t')
#             fields[details_ind] = json.loads(fields[details_ind])
#             yield dict(zip(header_fields, fields))
#         fileh.close()
# 
#     # create directory for static web files (CSS, javascript, etc)
#     web_dir = os.path.join(config.output_dir, 'web')
#     if not os.path.exists(web_dir):
#         logging.info("\tInstalling web files")
#         shutil.copytree(SRC_WEB_PATH, web_dir)
#     
#     report_html = 'out.html'
#     t = env.get_template('report.html')
#     fp = open(os.path.join(config.output_dir, report_html), 'w')
#     print >>fp, t.render(name=config.name,
#                          details_dir=rel_details_dir,
#                          results=parse_report_as_dicts(filename))
#     fp.close()
# 
# 
# 
# class Result(object):
#     '''    
#     '''
#     def __init__(self):
#         self.t_id = None
#         self.ss_id = None
#         
#         
#         self.weight_vec = None
#         self.sample_set = None
#         self.weights = None
#         self.samples = None
#         self.membership = None
#         self.weights_miss = None
#         self.weights_hit = None
#         self.es = 0.0
#         self.nes = 0.0
#         self.es_run_ind = 0
#         self.es_run = None
#         self.pval = 1.0
#         self.qval = 1.0
#         self.fwerp = 1.0
#         self.es_null = None
# 
#     def get_details_table(self):
#         rows = [['index', 'sample', 'rank', 'raw_weight', 
#                  'transformed_weight', 'running_es', 'core_enrichment']]
#         member_inds = (self.membership > 0).nonzero()[0]
#         for i,ind in enumerate(member_inds):
#             is_enriched = int(ind <= self.es_run_ind)
#             rows.append([i, self.samples[ind], ind+1, self.weights[ind],
#                          self.weights_hit[ind], self.es_run[ind], 
#                          is_enriched])
#         return rows
# 
#     def to_json(self):
#         '''
#         get json document representation of object
#         '''
#         member_inds = (self.membership > 0).nonzero()[0]
#         sample_set_size = len(member_inds)
#         num_misses = self.membership.shape[0] - sample_set_size
#         # calculate leading edge stats
#         if self.es < 0:
#             le_num_hits = sum(i >= self.es_run_ind for i in member_inds)
#             le_num_misses = self.membership.shape[0] - self.es_run_ind
#             if self.es_run_ind == 0:
#                 le_frac_hits = 0.0
#             else:
#                 le_frac_hits = float(le_num_hits) / self.es_run_ind
#         else:
#             le_num_hits = sum(i <= self.es_run_ind for i in member_inds)
#             le_num_misses = 1 + self.es_run_ind - le_num_hits
#             if self.es_run_ind == 0:
#                 le_frac_hits = 0.0
#             else:
#                 le_frac_hits = float(le_num_hits) / (1+self.es_run_ind)
#         sample_set_frac_le = float(le_num_hits) / sample_set_size
#         null_set_frac_le = float(le_num_misses) / num_misses
#         # get detailed report
#         rows = [['index', 'sample', 'rank', 'raw_weight', 
#                  'transformed_weight', 'running_es', 'core_enrichment']]
#         for i,ind in enumerate(member_inds):
#             is_enriched = int(ind <= self.es_run_ind)
#             rows.append([i, self.samples[ind], ind+1, self.weights[ind],
#                          self.weights_hit[ind], self.es_run[ind], 
#                          is_enriched])        
#         # build json document
#         d = {'name': self.weight_vec.name,
#              'desc': self.weight_vec.desc,
#              'sample_set_name': self.sample_set.name,
#              'sample_set_desc': self.sample_set.desc,
#              'sample_set_size': sample_set_size,
#              'es': self.es,
#              'nes': self.nes,
#              'nominal_p_value': self.pval,
#              'fdr_q_value': self.qval,
#              'fwer_p_value': self.fwerp,
#              'global_nes': 'NA',
#              'global_fdr_q_value': 'NA',
#              'rank_at_max': self.es_run_ind,
#              'leading_edge_num_hits': le_num_hits,
#              'leading_edge_frac_hits': le_frac_hits,
#              'sample_set_frac_in_leading_edge': sample_set_frac_le,
#              'null_set_frac_in_leading_edge': null_set_frac_le}
#         
# 
#     def get_report_fields(self, name, desc):
#         # calculate leading edge stats
#         member_inds = (self.membership > 0).nonzero()[0]
#         le_num_hits = sum(ind <= self.es_run_ind 
#                           for ind in member_inds)
#         le_num_misses = self.es_run_ind - le_num_hits
#         num_misses = self.membership.shape[0] - len(self.sample_set)
#         sample_set_frac_le = float(le_num_hits) / len(self.sample_set)
#         null_set_frac_le = float(le_num_misses) / num_misses
#         if self.es_run_ind == 0:
#             le_frac_hits = 0.0
#         else:
#             le_frac_hits = float(le_num_hits) / self.es_run_ind
#         # write result to text file            
#         fields = [name, desc,
#                   self.sample_set.name, self.sample_set.desc, 
#                   len(self.sample_set), self.es, self.nes, self.pval, 
#                   self.qval, self.fwerp, 'NA', 'NA',
#                   self.es_run_ind,
#                   le_num_hits, le_frac_hits, 
#                   sample_set_frac_le,
#                   null_set_frac_le, '{}']
#         return fields
# 
#         
# 
#     def plot_null_distribution(self, fig=None):
#         if fig is None:
#             fig = figure.Figure()
#         fig.clf()
#         percent_neg = (100. * (self.es_null < 0).sum() / 
#                        self.es_null.shape[0])
#         num_bins = int(round(float(self.es_null.shape[0]) ** (1./2.)))
#         #n, bins, patches = ax.hist(es_null, bins=num_bins, histtype='stepfilled')
#         ax = fig.add_subplot(1,1,1)
#         ax.hist(self.es_null, bins=num_bins, histtype='bar')
#         ax.axvline(x=self.es, linestyle='--', color='black')
#         ax.set_title('Random ES distribution')
#         ax.set_ylabel('P(ES)')
#         ax.set_xlabel('ES (Sets with neg scores: %.0f%%)' % (percent_neg))
#         return fig
# 
#     def plot(self, plot_conf_int=True, conf_int=0.95, fig=None):
#         if fig is None:
#             fig = figure.Figure()
#         fig.clf()
#         gs = gridspec.GridSpec(3, 1, height_ratios=[2,1,1])
#         # running enrichment score
#         ax0 = fig.add_subplot(gs[0])
#         x = np.arange(len(self.es_run))
#         y = self.es_run
#         ax0.plot(x, y, lw=2, color='blue', label='Enrichment profile')
#         ax0.axhline(y=0, color='gray')
#         ax0.axvline(x=self.es_run_ind, lw=1, linestyle='--', color='black')
#         # confidence interval
#         if plot_conf_int:
#             if np.sign(self.es) < 0:
#                 es_null_sign = self.es_null[self.es_null < 0]                
#             else:
#                 es_null_sign = self.es_null[self.es_null >= 0]                
#             # plot confidence interval band
#             es_null_mean = es_null_sign.mean()
#             es_null_low = quantile(es_null_sign, 1.0-conf_int)
#             es_null_hi = quantile(es_null_sign, conf_int)
#             lower_bound = np.repeat(es_null_low, len(x))
#             upper_bound = np.repeat(es_null_hi, len(x))
#             ax0.axhline(y=es_null_mean, lw=2, color='red', ls=':')
#             ax0.fill_between(x, lower_bound, upper_bound,
#                              lw=0, facecolor='yellow', alpha=0.5,
#                              label='%.2f CI' % (100. * conf_int))
#             # here we use the where argument to only fill the region 
#             # where the ES is above the confidence interval boundary
#             if np.sign(self.es) < 0:
#                 ax0.fill_between(x, y, lower_bound, where=y<lower_bound, 
#                                  lw=0, facecolor='blue', alpha=0.5)
#             else:
#                 ax0.fill_between(x, upper_bound, y, where=y>upper_bound, 
#                                  lw=0, facecolor='blue', alpha=0.5)
#         ax0.set_xlim((0,len(self.es_run)))
#         ax0.grid(True)
#         ax0.set_xticklabels([])
#         ax0.set_ylabel('Enrichment score (ES)')
#         ax0.set_title('Enrichment plot: %s' % (self.sample_set.name))
#         # membership in sample set
#         ax1 = fig.add_subplot(gs[1])
#         ax1.vlines(self.membership.nonzero()[0], ymin=0, ymax=1, lw=0.5, 
#                    color='black', label='Hits')
#         ax1.set_xlim((0,len(self.es_run)))
#         ax1.set_ylim((0,1))
#         ax1.set_xticks([])
#         ax1.set_yticks([])
#         ax1.set_xticklabels([])
#         ax1.set_yticklabels([])
#         ax1.set_ylabel('Set')
#         # weights
#         ax2 = fig.add_subplot(gs[2])
#         ax2.plot(self.weights_miss, color='blue')
#         ax2.plot(self.weights_hit, color='red')
#         ax2.set_xlim((0,len(self.es_run)))
#         ax2.set_xlabel('Samples')
#         ax2.set_ylabel('Weights')
#         # draw
#         fig.tight_layout()
#         return fig
#        
#     def get_details_table(self):
#         rows = [['index', 'sample', 'rank', 'raw_weight', 
#                  'transformed_weight', 'running_es', 'core_enrichment']]
#         member_inds = (self.membership > 0).nonzero()[0]
#         for i,ind in enumerate(member_inds):
#             is_enriched = int(ind <= self.es_run_ind)
#             rows.append([i, self.samples[ind], ind+1, self.weights[ind],
#                          self.weights_hit[ind], self.es_run[ind], 
#                          is_enriched])
#         return rows
# 
#     def get_report_fields(self, name, desc):
#         # calculate leading edge stats
#         member_inds = (self.membership > 0).nonzero()[0]
#         le_num_hits = sum(ind <= self.es_run_ind 
#                           for ind in member_inds)
#         le_num_misses = self.es_run_ind - le_num_hits
#         num_misses = self.membership.shape[0] - len(self.sample_set)
#         sample_set_frac_le = float(le_num_hits) / len(self.sample_set)
#         null_set_frac_le = float(le_num_misses) / num_misses
#         if self.es_run_ind == 0:
#             le_frac_hits = 0.0
#         else:
#             le_frac_hits = float(le_num_hits) / self.es_run_ind
#         # write result to text file            
#         fields = [name, desc,
#                   self.sample_set.name, self.sample_set.desc, 
#                   len(self.sample_set), self.es, self.nes, self.pval, 
#                   self.qval, self.fwerp, 'NA', 'NA',
#                   self.es_run_ind,
#                   le_num_hits, le_frac_hits, 
#                   sample_set_frac_le,
#                   null_set_frac_le, '{}']
#         return fields
#     




