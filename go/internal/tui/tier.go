package tui

import (
	"context"
	"fmt"
)

// StorageTier describes one S3 storage class with the cost figures shown in
// the tier selector.
type StorageTier struct {
	// Key is the S3 storage class name, e.g. "DEEP_ARCHIVE".
	Key           string
	Name          string
	StorageCost   string
	RetrievalTime string
	RetrievalCost string
	Description   string
}

// StorageTiers lists the selectable tiers in the order and with the cost
// information of the Python TableStorageTierSelector.STORAGE_TIERS table.
var StorageTiers = []StorageTier{
	{
		Key: "INTELLIGENT_TIERING", Name: "Intelligent-Tiering",
		StorageCost: "$2.50-23/TiB/mo", RetrievalTime: "Automatic",
		RetrievalCost: "$0", Description: "Automatic cost optimization",
	},
	{
		Key: "STANDARD_IA", Name: "Standard-IA",
		StorageCost: "$12.5/TiB/mo", RetrievalTime: "Milliseconds",
		RetrievalCost: "$10/TiB", Description: "Infrequent access, rapid retrieval",
	},
	{
		Key: "ONEZONE_IA", Name: "One Zone-IA",
		StorageCost: "$10/TiB/mo", RetrievalTime: "Milliseconds",
		RetrievalCost: "$10/TiB", Description: "Single AZ, lower cost IA",
	},
	{
		Key: "GLACIER_IR", Name: "Glacier Instant Retrieval",
		StorageCost: "$4/TiB/mo", RetrievalTime: "Milliseconds",
		RetrievalCost: "$10/TiB", Description: "Instant access to archives",
	},
	{
		Key: "GLACIER", Name: "Glacier Flexible Retrieval",
		StorageCost: "$3.6/TiB/mo", RetrievalTime: "3-5 hours",
		RetrievalCost: "$10/TiB", Description: "Low-cost archive, hours retrieval",
	},
	{
		Key: "DEEP_ARCHIVE", Name: "Glacier Deep Archive",
		StorageCost: "$1/TiB/mo", RetrievalTime: "12-48 hours",
		RetrievalCost: "$2.50/TiB", Description: "Lowest cost, long-term archive",
	},
}

// TierSelectorOptions parameterizes SelectStorageTier with the archive the
// tier change applies to.
type TierSelectorOptions struct {
	// CurrentTier is the archive's current storage class; it is excluded
	// from the selectable rows.
	CurrentTier    string
	Folder         string
	TotalSizeBytes int64
	ObjectCount    int64
}

var tierColumns = []Column{
	{Title: "Tier"}, {Title: "Storage Cost"}, {Title: "Retrieval Time"},
	{Title: "Retrieval Cost"}, {Title: "Description"},
}

// newTierModel builds the table model for SelectStorageTier and returns it
// together with the tiers shown (row index aligned).
func newTierModel(opts TierSelectorOptions) (*tableModel, []StorageTier) {
	shown := make([]StorageTier, 0, len(StorageTiers))
	for _, t := range StorageTiers {
		if t.Key == opts.CurrentTier {
			continue // no need to migrate to the same tier
		}
		shown = append(shown, t)
	}
	cells := make([][]string, len(shown))
	for i, t := range shown {
		cells[i] = []string{t.Name, t.StorageCost, t.RetrievalTime, t.RetrievalCost, t.Description}
	}
	sizeGiB := float64(opts.TotalSizeBytes) / (1 << 30)
	sizeTiB := sizeGiB / 1024

	m := newTableModel(TableConfig{
		Title: "Change Storage Tier",
		InfoLines: []string{
			fmt.Sprintf("Folder: %s", opts.Folder),
			fmt.Sprintf("Current tier: %s", opts.CurrentTier),
			fmt.Sprintf("Total size: %.2f GiB (%.3f TiB)", sizeGiB, sizeTiB),
			fmt.Sprintf("Object count: %d", opts.ObjectCount),
			"",
			"Available Storage Tiers:",
		},
		Columns: tierColumns,
		Rows:    cells,
		FooterLines: []string{
			"Note: Moving FROM Glacier/Deep Archive is not allowed",
			"Press Enter to select, Q/Esc to cancel",
		},
		Confirm: func(indices []int, _ [][]string) *ConfirmConfig {
			return tierConfirm(shown[indices[0]], opts, sizeGiB)
		},
	})
	return m, shown
}

// tierConfirm is the ScreenConfirmTierChange equivalent.
func tierConfirm(newTier StorageTier, opts TierSelectorOptions, sizeGiB float64) *ConfirmConfig {
	return &ConfirmConfig{
		Title: "Confirm Storage Tier Change",
		Body: []string{
			fmt.Sprintf("Folder: %s", opts.Folder),
			fmt.Sprintf("Current tier: %s", opts.CurrentTier),
			fmt.Sprintf("New tier: %s", newTier.Key),
			fmt.Sprintf("Objects to change: %d", opts.ObjectCount),
			fmt.Sprintf("Total size: %.2f GiB", sizeGiB),
			"",
			"This operation will change the storage class of all objects",
			"(except metadata files which remain in STANDARD)",
		},
		Buttons: []ConfirmButton{
			{Label: "Proceed", Action: ActionAccept},
			// Cancel returns to the tier table, like the Python
			// handle_confirmation which lets the user pick another
			// tier.
			{Label: "Cancel", Action: ActionReturn},
		},
	}
}

// SelectStorageTier shows the storage-tier table with cost information
// (Python TableStorageTierSelector) followed by a confirmation modal
// (ScreenConfirmTierChange). It returns the storage class key of the
// confirmed tier (e.g. "DEEP_ARCHIVE"), or "" when the user cancelled.
// The current tier is not offered. A missing TTY returns ErrNotInteractive.
func SelectStorageTier(ctx context.Context, opts TierSelectorOptions) (string, error) {
	m, shown := newTierModel(opts)
	final, err := runModel(ctx, m)
	if err != nil {
		return "", err
	}
	fm := final.(*tableModel)
	if fm.outcome != OutcomeSelected || len(fm.picked) == 0 {
		return "", nil
	}
	return shown[fm.picked[0]].Key, nil
}
