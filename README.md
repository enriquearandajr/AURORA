# AURORA: Affective User Recommendation Optimized for Real-time Audio

## Overview : 

Imagine a music-listening session where the next song is added to your queue based on your current cognitive state, without ever touching the keyboard. 

### Pipeline :

The user opens the AURORA app and connects their Spotify Premium account to be able to modify their queue and create a playlist in their account. Then, the user starts their Stream by selecting a song that matches their mood from a dataset of 50,000 songs which will create a new playlist in the user’s Spotify account with that song. They will wear a dry-electrode, non-invasive EEG cap that would records their EEG data while they listen to the song of their choice. Their EEG data will be removed of any artifacts, such as eye blinks or jaw clenches, and filtered in real-time and then fed into a cognitive state classifier model. This classifier will rate the incoming EEG data as “relaxed” or “focused”, in a scale from 0-100 where 0 is relaxed and 100 is focused. This arousal rating is one of the parameters to my custom music recommendation system, alongside the current song name, artist, and features. The features of the current song are found in that 50,000-song dataset, including danceability, energy, loudness, valence, tempo, and tags such as ‘calm’, ‘rock’, ‘joyful’. These features of the song are then normalized and nudged into the direction dictated by the user’s current mood through a series of algebraic computations, such as reducing the energy and loudness values if the user is in a relaxed state. After the computations, we take these new ideal features for our next song and encode them into a concentrated 16-dimensional embedding in latent space to be compared with the other songs in the dataset. This is done by comparing the cosine similarity between the latent embeddings and finds the top-k songs that are similar to the ideal features of the next song we’re looking for. We then decode the embedding of the features of the top song and query the Spotify ID from the 50,000-song dataset to add to our queue before the current song ends. The app also adds the upcoming song into the new playlist created for the session and this entire process will repeat over and over until the user stops their Stream, effectively creating a neurofeedback loop based on music.


### View the web app here (Still in development) :

[AURORA](https://enriquearandajr.github.io/Brain-DJ-Interface-Remixed/)

## Directory :

### backend :
Contains the notebooks, tools, src folders that powers the AURORA system

### frontend : 
Contains the app and media folders that present AURORA


## References:

[1] Starcke K, Mayr J, von Georgi R. Emotion Modulation through Music after Sadness Induction-The Iso Principle in a Controlled Experimental Study. Int J Environ Res Public Health. 2021 Nov 26;18(23):12486. doi: 10.3390/ijerph182312486. PMID: 34886210; PMCID: PMC8656869. https://pmc.ncbi.nlm.nih.gov/articles/PMC8656869/

[2] Ye Y, Zhu X, Li Y, Pan T, He W. Cross-subject EEG-based Emotion Recognition Using Adversarial Domain Adaption with Attention Mechanism. Annu Int Conf IEEE Eng Med Biol Soc. 2021 Nov;2021:1140-1144. doi: 10.1109/EMBC46164.2021.9630777. PMID: 34891489. https://pubmed.ncbi.nlm.nih.gov/34891489/

[3] Wei-Long Zheng, and Bao-Liang Lu, Investigating Critical Frequency Bands and Channels for EEG-based Emotion Recognition with Deep Neural Networks, accepted by IEEE Transactions on Autonomous Mental Development (IEEE TAMD) 7(3): 162-175, 2015. https://www.researchgate.net/publication/276443876_Investigating_Critical_Frequency_Bands_and_Channels_for_EEG-Based_Emotion_Recognition_with_Deep_Neural_Networks

[4] Ruo-Nan Duan, Jia-Yi Zhu and Bao-Liang Lu, Differential Entropy Feature for EEG-based Emotion Classification, Proc. of the 6th International IEEE EMBS Conference on Neural Engineering (NER). 2013: 81-84. https://bcmi.sjtu.edu.cn/home/zhujiayi/pdf/NER2013.pdf)

[5] Trost, Wiebke, et al. "Live music stimulates the affective brain and emotionally entrains listeners in real time." *Proceedings of the National Academy of Sciences*, vol. 121, no. 10, 2024, p. e2316306121. https://doi.org/10.1073/pnas.2316306121

[6] Yoo, Gilsang, et al. "Prediction of Cognitive Load from Electroencephalography Signals Using Long Short-Term Memory Network." *Bioengineering*, vol. 10, no. 3, 2023, p. 361. *MDPI*, **https://www.mdpi.com/2306-5354/10/3/361**

[7] Juslin, Patrik N. "From Everyday Emotions to Aesthetic Emotions: Towards a Unified Theory of Musical Emotions." *Physics of Life Reviews*, vol. 10, no. 3, 2013, pp. 235-266. *ScienceDirect*, https://www.sciencedirect.com/science/article/pii/S1571064513000638
