/*
Query 7: Domestic 5G data usage in MB.

Output:
{
  service_type: "Data",
  charge_type: "Data MO",
  data_type: "5G",
  mou_mbs: 442060714
}
*/

db.{{request_log}}.aggregate([
  {
    $match: {
      req_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      rat_type: "5G",
      roaming_destination_id: 87,
      rating_group: { $nin: ["500003"] }
    }
  },
  {
    $group: {
      _id: null,
      total_bytes: {
        $sum: {
          $toDecimal: { $ifNull: ["$act_update_used_volume", 0] }
        }
      }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "Data" },
      charge_type: { $literal: "Data MO" },
      data_type: { $literal: "5G" },
      mou_mbs: {
        $round: [
          {
            $divide: [
              "$total_bytes",
              { $toDecimal: 1048576 }
            ]
          },
          2
        ]
      }
    }
  }
]);
