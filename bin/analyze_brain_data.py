"""Analyze Brain Data

Usage:
    analyze_brain_data.py <query_data> <db_data> <model> <baseline> [ --out=<path> ]

Options:
    -h --help     Show this screen.
    --out=<path>  Path to save output to. 'None' means a time-stamped folder
                  will automatically be created. [default: None]
"""
import math
from collections import defaultdict, Counter
from itertools import groupby as g
from os import makedirs, remove
# import pdb; pdb.set_trace()
from os.path import join, basename, normpath, exists

import matplotlib
import numpy as np
import pandas as pd
from docopt import docopt
from scipy.spatial import distance
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn
seaborn.set()
from scipy.stats import binom_test

from scrna_nn.data_container import DataContainer
from scrna_nn.reduce import _reduce_helper
from scrna_nn import util
# analyze queries

# arg1: query hdf5 file
# arg2: database hdf5 file
# arg3: model
# arg4: baseline_model
# arg3: output folder

# Setting up the colors and legend for all plots ahead of time:
classes_ordered = ['control_3m', 'control_3m_1w','control_3m_2w', 'control_4m_2w', 'disease_3m', 'disease_3m_1w', 'disease_3m_2w', 'disease_4m_2w']
# # Two toned color map
# color_map = {'control_3m': '#66ff66',
#              'control_3m_1w': '#33cc00',
#              'control_3m_2w': '#339900',
#              'control_4m_2w': '#006600',
#              'disease_3m': '#66ffff',
#              'disease_3m_1w': '#6699ff',
#              'disease_3m_2w': '#3300ff',
#              'disease_4m_2w': '#6600ff'}

color_map = {'control_3m': '#66ffff',
             'control_3m_1w': '#6699ff',
             'control_3m_2w': '#6600ff',
             'control_4m_2w': '#ff00cc',
             'disease_3m': '#33ff00',
             'disease_3m_1w': '#ffff00',
             'disease_3m_2w': '#ff9900',
             'disease_4m_2w': '#ff0000'}

legend_circles = []
for cls in classes_ordered:
        color = color_map[cls]
        #circ = mpatches.Circle((0,0), 1, fc=matplotlib.colors.to_rgba(color))
        circ = mpatches.Circle((0,0), 1, fc=color)
        legend_circles.append(circ)

def plot(X, name, working_dir, labels):
        # set up colors
        #colors = [matplotlib.colors.to_rgba(color_map[label]) for label in labels]
        #colors = np.array(colors).reshape((len(colors), 1))
        colors = [color_map[label] for label in labels]
        # colors = ['g' for label in labels]
        #colors = matplotlib.colors.to_rgba_array(colors)
        plt.figure()
        plt.scatter(X[:, 0], X[:, 1], c=colors, alpha=0.65)
        plt.title(name)
        plt.xlabel("component 1")
        plt.ylabel("component 2")
        plt.legend(legend_circles, classes_ordered, ncol=2, bbox_to_anchor=(1.04, 0.5), loc='center left')
        plt.savefig(join(working_dir, name+".pdf"), bbox_inches="tight")
        plt.savefig(join(working_dir, name+".png"), bbox_inches="tight")
        plt.close()

def plot_consolidated_labels(X, name, working_dir, labels):
        colors = []
        for l in labels:
                if 'control' in l:
                        colors.append('b')
                elif 'disease' in l:
                        colors.append('r')
        circles = [mpatches.Circle((0,0), 1, fc='b'), mpatches.Circle((0,0), 1, fc='r')]
        plt.figure()
        plt.scatter(X[:, 0], X[:, 1], c=colors, alpha=0.65)
        plt.title(name)
        plt.xlabel("component 1")
        plt.ylabel("component 2")
        plt.legend(circles, ['control', 'disease'], ncol=2, bbox_to_anchor=(1.04, 0.5), loc='center left')
        plt.savefig(join(working_dir, name+"_consolidated.pdf"), bbox_inches="tight")
        plt.savefig(join(working_dir, name+"_consolidated.png"), bbox_inches="tight")
        plt.close()
        
def visualize(data, name, working_dir, labels):
        pca = PCA(n_components=2)
        x = pca.fit_transform(data)
        plot(x, name+"_PCA", working_dir, labels)
        plot_consolidated_labels(x, name+"_PCA", working_dir, labels)
        tsne = TSNE(n_components=2)
        x = tsne.fit_transform(data)
        plot(x, name+"_TSNE", working_dir, labels)
        plot_consolidated_labels(x, name+"_TSNE", working_dir, labels)

def load_data(args):
        query_data = DataContainer(args['<query_data>'])
        db_data = DataContainer(args['<db_data>'])
        raw_query = query_data.get_expression_mat()
        query_labels = query_data.get_labels()
        raw_db = db_data.get_expression_mat()
        db_labels = db_data.get_labels()
        db_cell_ids = db_data.get_cell_ids()
        return raw_query, query_labels, raw_db, db_labels, db_cell_ids, query_data

def write_enriched_data(all_dataframe, cells_to_keep, path):
        new_df = all_dataframe.loc[cells_to_keep]
        print("{} , cells:{}".format(path, new_df.shape[0]))
        if exists(path):
                remove(path)
        h5_store = pd.HDFStore(path)
        h5_store['rpkm'] = new_df
        h5_store.close()

# def load_model_details(folder):
#       training_args_path = join(folder, "command_line_args.json")
#       with open(training_args_path, 'r') as fp:
#               training_args = json.load(fp)
#       mean = None
#       std = None
#       if training_args['--gn']:
#               mean = pd.read_pickle(join(folder, "mean.p"))
#               std = pd.read_pickle(join(folder, "std.p"))
#       return training_args, mean, std

def reduce_dimensions(args):
        query_reduced_by_model, _ = _reduce_helper(args['<model>'], args['<query_data>'])
        db_reduced_by_model, _ = _reduce_helper(args['<model>'], args['<db_data>'])
        query_reduced_by_baseline, _ = _reduce_helper(args['<baseline>'], args['<query_data>'])
        db_reduced_by_baseline, _ = _reduce_helper(args['<baseline>'], args['<db_data>'])
        return query_reduced_by_model, db_reduced_by_model, query_reduced_by_baseline, db_reduced_by_baseline

def nearest_dist_to_each_type(distances, labels):
        min_distances = {}
        for dist, label in zip(distances, labels):
                if label not in min_distances:
                        min_distances[label] = dist
        return min_distances

def make_nearest_dist_per_db_type_plots(d, working_dir):
        working_dir = join(working_dir, "A_nearest_dist_per_db_type")
        if not exists(working_dir):
                makedirs(working_dir)
        for query_type, nearest_to_db_types_d in d.items():
                avgs_labels = []
                avgs_values = []
                for db_type, nearest_distances in nearest_to_db_types_d.items():
                        avgs_labels.append(db_type)
                        avgs_values.append(np.mean(nearest_distances))
                avgs_labels = np.array(avgs_labels)
                avgs_values = np.array(avgs_values)
                sort_idx = np.argsort(avgs_values)
                avgs_labels = avgs_labels[sort_idx]
                avgs_values = avgs_values[sort_idx]

                plt.figure()
                plt.bar(np.arange(1, len(avgs_labels)+1), avgs_values, tick_label=avgs_labels)
                plt.xticks(rotation='vertical', fontsize=8)
                plt.title("Avg of nearest distances to each DB type")
                plt.savefig(join(working_dir, query_type+".pdf"), bbox_inches="tight")
                plt.savefig(join(working_dir, query_type+".png"), bbox_inches="tight")
                plt.close()
                

def make_top_5_labels_plots(d, working_dir):
        working_dir = join(working_dir, "B_top_5_label_frequencies")
        if not exists(working_dir):
                makedirs(working_dir)
        for query_type, top_fives in d.items():
                db_types, counts = np.unique(top_fives, return_counts=True)
                sort_idx = np.argsort(counts)[::-1]
                db_types = db_types[sort_idx]
                counts = counts[sort_idx]
                plt.figure()
                plt.bar(np.arange(1, len(db_types)+1), counts, tick_label=db_types)
                plt.xticks(rotation='vertical', fontsize=8)
                plt.title("# of times each DB type appeared in top 5 results")
                plt.savefig(join(working_dir, query_type+".pdf"), bbox_inches="tight")
                plt.savefig(join(working_dir, query_type+".png"), bbox_inches="tight")
                plt.close()

def make_5_nearest_distances_plots(d, working_dir):
        working_dir = join(working_dir, "C_nearest_5_distances")
        if not exists(working_dir):
                makedirs(working_dir)
        for query_type, avg_nearest_distances in d.items():
                plt.figure()
                plt.hist(avg_nearest_distances, bins='auto')
                plt.title("Hist, avg top 5 nearest distances, mean={}".format(np.mean(avg_nearest_distances)))
                plt.savefig(join(working_dir, query_type+".pdf"), bbox_inches="tight")
                plt.savefig(join(working_dir, query_type+".png"), bbox_inches="tight")
                plt.close()

def make_classification_histograms(overall_classifications, classifications, working_dir):
        working_dir = join(working_dir, "D_classification_histograms")
        if not exists(working_dir):
                makedirs(working_dir)
        db_types, counts = np.unique(overall_classifications, return_counts=True)
        sort_idx = np.argsort(counts)[::-1]
        db_types = db_types[sort_idx]
        counts = counts[sort_idx]
        plt.figure()
        plt.bar(np.arange(1, len(db_types)+1), counts, tick_label=db_types)
        plt.xticks(rotation='vertical', fontsize=8)
        plt.title("# of query cells that are classified as each cell type")
        plt.savefig(join(working_dir, "overall.pdf"), bbox_inches="tight")
        plt.savefig(join(working_dir, "overall.png"), bbox_inches="tight")
        plt.close()
        control_clfs = []
        disease_clfs = []
        for query_type, clfs in classifications.items():
                db_types, counts = np.unique(clfs, return_counts=True)
                sort_idx = np.argsort(counts)[::-1]
                db_types = db_types[sort_idx]
                counts = counts[sort_idx]
                plt.figure()
                plt.bar(np.arange(1, len(db_types)+1), counts, tick_label=db_types)
                plt.xticks(rotation='vertical', fontsize=8)
                plt.title("# of query cells that are classified as each cell type")
                plt.savefig(join(working_dir, query_type+".pdf"), bbox_inches="tight")
                plt.savefig(join(working_dir, query_type+".png"), bbox_inches="tight")
                plt.close()
                if 'control' in query_type:
                        control_clfs.extend(clfs)
                elif 'disease' in query_type:
                        disease_clfs.extend(clfs)
        db_types_control, counts_control = np.unique(control_clfs, return_counts=True)
        sort_idx = np.argsort(counts_control)[::-1]
        db_types_control = db_types_control[sort_idx]
        counts_control = counts_control[sort_idx]
        plt.figure()
        plt.bar(np.arange(1, len(db_types_control)+1), counts_control, tick_label=db_types_control)
        plt.xticks(rotation='vertical', fontsize=8)
        plt.title("# of query cells that are classified as each cell type")
        plt.savefig(join(working_dir, "control_all.pdf"), bbox_inches="tight")
        plt.savefig(join(working_dir, "control_all.png"), bbox_inches="tight")
        plt.close()
        db_types_disease, counts_disease = np.unique(disease_clfs, return_counts=True)
        sort_idx = np.argsort(counts_disease)[::-1]
        db_types_disease = db_types_disease[sort_idx]
        counts_disease = counts_disease[sort_idx]
        plt.figure()
        plt.bar(np.arange(1, len(db_types_disease)+1), counts_disease, tick_label=db_types_disease)
        plt.xticks(rotation='vertical', fontsize=8)
        plt.title("# of query cells that are classified as each cell type")
        plt.savefig(join(working_dir, "disease_all.pdf"), bbox_inches="tight")
        plt.savefig(join(working_dir, "disease_all.png"), bbox_inches="tight")
        plt.close()

        # merge the cases
        merged_db_types = np.union1d(db_types_control, db_types_disease)
        control_counts = []
        for label in merged_db_types:
                count = 0
                for c in control_clfs:
                        if c == label:
                                count += 1
                control_counts.append(count)
        control_counts = np.array(control_counts, dtype=float)
        print(control_counts)
        control_fracs = control_counts / len(control_clfs)
        disease_counts = []
        for label in merged_db_types:
                count = 0
                for c in disease_clfs:
                        if c == label:
                                count += 1
                disease_counts.append(count)
        disease_counts = np.array(disease_counts, dtype=float)
        print(disease_counts)
        disease_fracs = disease_counts / len(disease_clfs)
        plt.figure()
        x_locations = np.arange(1, len(merged_db_types)+1)
        width = 0.35
        labels_sort_idx = np.argsort(control_fracs)[::-1]
        merged_db_types = merged_db_types[labels_sort_idx]
        disease_fracs = disease_fracs[labels_sort_idx]
        disease_counts = disease_counts[labels_sort_idx]
        control_fracs = control_fracs[labels_sort_idx]
        control_counts = control_counts[labels_sort_idx]
        merged_db_types = [' '.join(name.split()[1:]) for name in merged_db_types]
        merged_db_types = np.array(merged_db_types)
        rects1 = plt.bar(x_locations, control_fracs, width, color='b', label='control')
        rects2 = plt.bar(x_locations + width, disease_fracs, width, color='r', label='disease')
        #plt.bar(np.arange(1, len(merged_db_types)+1), disease_counts, tick_label=merged_db_types, color='r', label='disease')
        plt.xticks(x_locations + width / 2, merged_db_types, rotation='vertical', fontsize=8)
        plt.ylabel('Fraction of query cells')
        plt.legend()
        plt.title("Portion of query cells classified as each cell type")
        # add p-vals
        for rect1, rect2 in zip(rects1, rects2):
                height1 = rect1.get_height()
                height2 = rect2.get_height()
                count1 = math.floor(1000*height1)
                count2 = math.floor(1000*height2)
                pval = binom_test(count1, count1+count2, p=0.5)
                plt.gca().text(rect1.get_x(), 1.05*max(height1,height2), '{:.2e}'.format(pval), ha='left', va='bottom', fontsize=7)
        plt.savefig(join(working_dir, "grouped_bar.pdf"), bbox_inches="tight")
        plt.savefig(join(working_dir, "grouped_bar.png"), bbox_inches="tight")
        plt.close()
        # Fisher's test comparing the two (control vs disease)
        contingency_table = np.stack((control_counts, disease_counts), axis=0)
        np.save('contingency_table', contingency_table)
        np.savetxt('contingency_table.csv', contingency_table, delimiter=',')
        print(contingency_table.shape)
        

        keep = [i for i in range(contingency_table.shape[1]) if 0 not in contingency_table[:, i]]
        merged_db_types = merged_db_types[keep]
        control_counts = control_counts[keep]
        control_fracs = control_counts / np.sum(control_counts)
        disease_counts = disease_counts[keep]
        disease_fracs = disease_counts / np.sum(disease_counts)
        contingency_table = np.stack((control_counts, disease_counts), axis=0)
        x_locations = np.arange(1, len(merged_db_types)+1)
        plt.figure()
        rects1 = plt.bar(x_locations, control_fracs, width, color='b', label='control')
        rects2 = plt.bar(x_locations + width, disease_fracs, width, color='r', label='disease')
        plt.xticks(x_locations + width / 2, merged_db_types, rotation='vertical', fontsize=8)
        plt.ylabel('Fraction of query cells')
        plt.legend()
        plt.title("Portion of query cells classified as each cell type")
        for rect1, rect2 in zip(rects1, rects2):
                height1 = rect1.get_height()
                height2 = rect2.get_height()
                count1 = math.floor(1000*height1)
                count2 = math.floor(1000*height2)
                pval = binom_test(count1, count1+count2, p=0.5)
                plt.gca().text(rect1.get_x(), 1.05*max(height1,height2), '{:.2e}'.format(pval), ha='left', va='bottom', fontsize=7)
        plt.savefig(join(working_dir, "grouped_bar_non_zero.pdf"), bbox_inches="tight")
        plt.savefig(join(working_dir, "grouped_bar_non_zero.png"), bbox_inches="tight")
        plt.close()
        np.save('contingency_table2', contingency_table)
        np.savetxt('contingency_table_no_zeros.csv', contingency_table, delimiter=',')
        print(contingency_table.shape)

                
def enriched_brain_cortex_plot_and_data(count_list, top_5_nearest_cells_d, threshold, working_dir):
        counts = [x[1] for x in count_list]
        plt.figure()
        plt.hist(counts, bins='auto')
        plt.title("Hist, counts of brain/cortex in 100 nearest neighbors for each query")
        plt.savefig(join(working_dir, "brain_cortex_histogram.pdf"), bbox_inches="tight")
        plt.savefig(join(working_dir, "brain_cortex_histogram.png"), bbox_inches="tight")
        plt.close()

        keep = []
        print("Keeping: bmw_osteocyte_count")
        with open(join(working_dir, "brain_cortex_nearest_hits.txt"), 'w') as f:
                for item in count_list:
                        if item[1] > threshold:
                                print("{}: {}".format(item[0], item[2]))
                                keep.append(item[0])
                                f.write("{}:\n".format(item[0]))
                                f.write("\t{}\n\t{}\n\t{}\n\t{}\n\t{}\n".format(top_5_nearest_cells_d[item[0]][0], top_5_nearest_cells_d[item[0]][1],top_5_nearest_cells_d[item[0]][2],top_5_nearest_cells_d[item[0]][3],top_5_nearest_cells_d[item[0]][4]))
        return keep

def classify(sorted_neighbors):
        # Adapted from https://stackoverflow.com/a/1520716
        sorted_neighbors = sorted_neighbors.tolist()
        return max(g(sorted(sorted_neighbors)), key=lambda xv:(len(list(xv[1])),-sorted_neighbors.index(xv[0])))[0]
        

def main(args):
        working_dir = util.create_working_directory(args['--out'], 'mouse_brain_analysis/')
        model_name = basename(normpath(args['<model>']))
        baseline_name = basename(normpath(args['<baseline>']))
        raw_query, query_labels, raw_db, db_labels, db_cell_ids, query_data_container = load_data(args)
        # 1, visualize the data using 2D PCA and 2D t-SNE
        visualize(raw_query, "original_query_data", working_dir, query_labels)
        # 2, reduce dimensions of data using the trained models, visualize using 2D PCA and 2D t-sne
        query_model, db_model, query_baseline, db_baseline = reduce_dimensions(args)
        visualize(query_baseline, baseline_name+"_reduced", working_dir, query_labels)
        visualize(query_model, model_name+"_reduced", working_dir, query_labels)

        brain_cortex_in_top_100 = []
        brain_cortex_in_top_10 = []
        brain_cortex_in_top_5 = []
        brain_cortex_in_top_1 = []
        brain_cortex_counts = [] # tuples (sample_ID, count_of_brain_cortex_in_top_100, count_of_bone_marrow_osteocyte_in_top_100)
        top_5_nearest_cells = defaultdict(list)
        
        nearest_dist_per_type_dict = defaultdict(lambda: defaultdict(list))
        top_5_types_dict = defaultdict(list)
        avg_nearest_5_distances_dict = defaultdict(list)
        classifications = defaultdict(list)
        overall_classifications = []
        
        dist_model = distance.cdist(query_model, db_model, metric='euclidean')
        for index, distances_to_query in enumerate(dist_model):
                query_label = query_labels[index]
                sorted_distances_indices = np.argsort(distances_to_query)
                sorted_distances = distances_to_query[sorted_distances_indices]
                sorted_labels = db_labels[sorted_distances_indices]
                sorted_cell_ids = db_cell_ids[sorted_distances_indices]

                top_5_nearest_cells[query_data_container.rpkm_df.index[index]] = sorted_cell_ids[:5]
                # Check if brain/cortex is in there
                if sorted_labels[0] == 'UBERON:0000955 brain' or sorted_labels[0] == 'UBERON:0001851 cortex':
                        brain_cortex_in_top_1.append(query_data_container.rpkm_df.index[index])
                top_5_l = sorted_labels[:5]
                if 'UBERON:0000955 brain' in top_5_l or 'UBERON:0001851 cortex' in top_5_l:
                        brain_cortex_in_top_5.append(query_data_container.rpkm_df.index[index])
                top_10_l = sorted_labels[:10]
                if 'UBERON:0000955 brain' in top_10_l or 'UBERON:0001851 cortex' in top_10_l:
                        brain_cortex_in_top_10.append(query_data_container.rpkm_df.index[index])
                top_100_l = sorted_labels[:100]
                if 'UBERON:0000955 brain' in top_100_l or 'UBERON:0001851 cortex' in top_100_l:
                        brain_cortex_in_top_100.append(query_data_container.rpkm_df.index[index])

                counts = Counter(sorted_labels[:100])
                brain_cortex_counts.append((query_data_container.rpkm_df.index[index], counts['UBERON:0000955 brain']+counts['UBERON:0001851 cortex'], counts['CL:0002092 bone marrow cell']+counts['CL:0000137 osteocyte']))
                
                min_distances = nearest_dist_to_each_type(sorted_distances, sorted_labels)
                for db_type, min_dist in min_distances.items():
                        nearest_dist_per_type_dict[query_label][db_type].append(min_dist)

                top_5_types = sorted_labels[:5]
                top_5_types_dict[query_label].extend(top_5_types)

                avg_top_5_distances = np.mean(sorted_distances[:5])
                avg_nearest_5_distances_dict[query_label].append(avg_top_5_distances)

                classified_label = classify(sorted_labels[:100])
                overall_classifications.append(classified_label)
                classifications[query_label].append(classified_label)
                
        make_nearest_dist_per_db_type_plots(nearest_dist_per_type_dict, working_dir)
        make_top_5_labels_plots(top_5_types_dict, working_dir)
        make_5_nearest_distances_plots(avg_nearest_5_distances_dict, working_dir)
        make_classification_histograms(overall_classifications, classifications, working_dir)
        enriched = enriched_brain_cortex_plot_and_data(brain_cortex_counts, top_5_nearest_cells, 70, working_dir)

        # write_enriched_data(query_data_container.rpkm_df, brain_cortex_in_top_100, join(working_dir, 'brain_cortex_in_top_100.hdf5'))
        # write_enriched_data(query_data_container.rpkm_df, brain_cortex_in_top_10, join(working_dir, 'brain_cortex_in_top_10.hdf5'))
        # write_enriched_data(query_data_container.rpkm_df, brain_cortex_in_top_5, join(working_dir, 'brain_cortex_in_top_5.hdf5'))
        # write_enriched_data(query_data_container.rpkm_df, brain_cortex_in_top_1, join(working_dir, 'brain_cortex_in_top_1.hdf5'))
        write_enriched_data(query_data_container.rpkm_df, enriched, join(working_dir, 'brain_cortex_threshold_70_out_of_100.hdf5'))

        

if __name__ == "__main__":
        args = docopt(__doc__)
        print(args)
        main(args)
